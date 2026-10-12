"""python -m gateway pair <CODE> | run | unpair   (from webapp/backend)

`run` first catches up on readings missed while the gateway was off (up to
--catch-up-days, at 15-minute resolution, like a logger's store-and-forward
buffer), then produces a live reading every --interval seconds.

Console commands while running (or write them, one per line, to
gateway/commands.txt -- handy from a second terminal during a demo):
    status                      inverter outputs, faults, upload queue
    inject INV-3 30 [2h|45m]    derate an inverter by 30% (until cleared, or for a duration)
    clear [INV-3]               end injected faults (all, or one inverter)
    offline [10m]               simulate a lost internet link: readings queue up
    online                      reconnect now (the queue is uploaded)
    quit
"""

import argparse
import math
import re
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import requests

from .client import Cloud, GatewayError, load_state, new_serial, save_state, STATE_FILE
from .plant import VirtualPlant, iso
from .weather_feed import LiveWeather, fetch_weather_15min

COMMAND_FILE = Path(__file__).resolve().parent / "commands.txt"
CATCH_UP_STEP_MINUTES = 15


def parse_duration(text: str) -> pd.Timedelta:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([smh])", text.strip().lower())
    if not m:
        raise ValueError(f"Bad duration {text!r}; use e.g. 30s, 10m, 2h")
    return pd.Timedelta(float(m.group(1)), unit={"s": "s", "m": "min", "h": "h"}[m.group(2)])


def now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC").floor("s")


class Gateway:
    def __init__(self, cloud: Cloud, plant: VirtualPlant, interval_s: int, serial: str):
        self.cloud, self.plant, self.interval_s, self.serial = cloud, plant, interval_s, serial
        self.live_weather = LiveWeather(plant.lat, plant.lon)
        self.weather_queue: list[dict] = []
        self.reading_queue: list[dict] = []
        self.offline_until: pd.Timestamp | None = None
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.last_tick: pd.Timestamp | None = None

    # ------------------------------------------------------------ uploads

    def flush(self) -> None:
        if self.offline_until is not None:
            if now_utc() < self.offline_until:
                return
            self.offline_until = None
            print(f"  link restored -- uploading {len(self.reading_queue)} queued readings")
        if not self.weather_queue and not self.reading_queue:
            self.cloud.ingest([], [])  # heartbeat
            return
        weather, readings = self.weather_queue, self.reading_queue
        try:
            self.cloud.ingest(weather, readings)
        except (requests.RequestException, GatewayError) as e:
            print(f"  upload failed, will retry ({e})")
            return
        self.weather_queue, self.reading_queue = [], []

    # ------------------------------------------------------------ catch-up

    def catch_up(self, last_recorded_at: str | None, max_days: int) -> None:
        now = now_utc()
        earliest = now - pd.Timedelta(days=max_days)
        last = pd.Timestamp(last_recorded_at) if last_recorded_at else earliest
        last = max(last, earliest)
        if now - last <= pd.Timedelta(minutes=CATCH_UP_STEP_MINUTES):
            print("Up to date -- no catch-up needed.")
            return

        past_days = min(math.ceil((now - last) / pd.Timedelta(days=1)) + 1, 92)
        print(f"Catching up from {iso(last)} ({(now - last) / pd.Timedelta(hours=1):.1f} h missed)...")
        weather = fetch_weather_15min(self.plant.lat, self.plant.lon, past_days)
        weather = weather[(weather["timestamp"] > last) & (weather["timestamp"] <= now)]
        if weather.empty:
            return
        physics = self.plant.physics(weather.reset_index(drop=True), CATCH_UP_STEP_MINUTES)
        for _, row in physics.iterrows():
            w, r = self.plant.step(row, CATCH_UP_STEP_MINUTES)
            self.weather_queue.append(w)
            self.reading_queue.extend(r)
        n = len(self.reading_queue)
        self.flush()
        print(f"Caught up: {len(physics)} intervals, {n} readings uploaded.")

    # ------------------------------------------------------------ live

    def tick(self, ts: pd.Timestamp) -> None:
        values = self.live_weather.at(ts)
        frame = pd.DataFrame([{"timestamp": ts, **values}])
        row = self.plant.physics(frame, self.interval_s / 60).iloc[0]
        with self.lock:
            w, r = self.plant.step(row, self.interval_s / 60)
            self.weather_queue.append(w)
            self.reading_queue.extend(r)
            self.last_tick = ts
            self.flush()
        outputs = "  ".join(f"{inv.label} {inv.last_ac_kw:5.2f}" for inv in self.plant.inverters)
        link = "OFFLINE (queued)" if self.offline_until else "sent"
        print(f"{ts.strftime('%H:%M:%S')}Z  {outputs}  kW  [{link}]")

    def run_live(self) -> None:
        interval = pd.Timedelta(seconds=self.interval_s)
        while not self.stop.is_set():
            next_tick = now_utc().ceil(interval)
            if self.last_tick is not None:
                next_tick = max(next_tick, self.last_tick + interval)  # never the same tick twice
            # Event.wait can return a few ms early; keep waiting until the tick is due.
            while (remaining := (next_tick - pd.Timestamp.now(tz="UTC")).total_seconds()) > 0:
                if self.stop.wait(remaining):
                    return
            self.read_command_file()
            try:
                self.tick(next_tick)
            except (requests.RequestException, GatewayError) as e:
                print(f"  tick {iso(next_tick)} skipped: {e}")

    # ------------------------------------------------------------ console

    def read_command_file(self) -> None:
        if COMMAND_FILE.exists():
            lines = COMMAND_FILE.read_text().splitlines()
            COMMAND_FILE.unlink()
            for line in lines:
                if line.strip():
                    print(f"> {line.strip()}  (from {COMMAND_FILE.name})")
                    self.command(line)

    def command(self, line: str) -> bool:
        """Runs one console command; returns False on quit."""
        parts = line.split()
        if not parts:
            return True
        cmd, args = parts[0].lower(), parts[1:]
        try:
            with self.lock:
                if cmd in ("quit", "exit"):
                    return False
                elif cmd == "status":
                    self.print_status()
                elif cmd == "inject" and len(args) >= 2:
                    loss = float(args[1].rstrip("%")) / 100
                    if not 0 < loss <= 1:
                        raise ValueError("loss must be between 0 and 100%")
                    until = now_utc() + parse_duration(args[2]) if len(args) > 2 else None
                    self.plant.inject(args[0], loss, until)
                    print(f"  {args[0].upper()} derated by {loss:.0%}" + (f" until {iso(until)}" if until else " until cleared"))
                elif cmd == "clear":
                    self.plant.clear(args[0] if args else None)
                    print(f"  cleared {'faults on ' + args[0].upper() if args else 'all faults'}")
                elif cmd == "offline":
                    duration = parse_duration(args[0]) if args else pd.Timedelta(hours=24)
                    self.offline_until = now_utc() + duration
                    print(f"  link down until {iso(self.offline_until)} (type `online` to reconnect)")
                elif cmd == "online":
                    if self.offline_until is not None:
                        self.offline_until = now_utc()
                        self.flush()
                else:
                    print(__doc__.split("Console commands", 1)[1].split("\n", 1)[1])
        except (KeyError, ValueError) as e:
            print(f"  {e}")
        return True

    def print_status(self) -> None:
        print(f"  gateway {self.serial}, interval {self.interval_s}s, "
              f"last reading {iso(self.last_tick) if self.last_tick else '-'}, "
              f"queued {len(self.reading_queue)}" + (", OFFLINE" if self.offline_until else ""))
        for inv in self.plant.inverters:
            fault = ""
            if inv.fault:
                kind = "injected" if inv.manual_fault else "random"
                until = iso(inv.fault.until) if inv.fault.until else "cleared"
                fault = f"  fault {inv.fault.loss:.0%} ({kind}, until {until})"
            print(f"  {inv.label}: {inv.last_ac_kw:.3f} kW, today {inv.energy_today_kwh:.2f} kWh{fault}")


def cmd_pair(args: argparse.Namespace) -> None:
    serial = args.serial or new_serial()
    result = Cloud().pair(args.code, serial)
    save_state(result["token"], serial)
    plant, inverters = result["plant"], result["inverters"]
    print(f"Paired {serial} with '{plant['name']}' ({len(inverters)} inverters: "
          f"{', '.join(i['label'] for i in inverters)}).")
    print(f"Device token saved to {STATE_FILE}. Next: python -m gateway run")


def cmd_run(args: argparse.Namespace) -> None:
    state = load_state()
    cloud = Cloud(state["token"])
    config = cloud.state()
    plant = VirtualPlant(config["plant"], config["inverters"],
                         random_faults=not args.no_random_faults, seed=args.seed)
    gateway = Gateway(cloud, plant, args.interval, state["serial"])
    print(f"Gateway {state['serial']} -> '{config['plant']['name']}' "
          f"({len(plant.inverters)} inverters, {plant.cfg['capacity_kw']:.1f} kW) -- SIMULATED DEVICE")

    gateway.catch_up(config.get("last_recorded_at"), args.catch_up_days)
    worker = threading.Thread(target=gateway.run_live, daemon=True)
    worker.start()
    print(f"Live: a reading every {args.interval}s. Type `help` for commands, `quit` to stop.")

    try:
        while worker.is_alive():
            try:
                line = input()
            except EOFError:  # no console attached (e.g. started in the background)
                worker.join()
                break
            if not gateway.command(line):
                break
    except KeyboardInterrupt:
        pass
    gateway.stop.set()
    print("Stopped.")


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m gateway", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    pair = sub.add_parser("pair", help="pair with a plant using the code shown in the app")
    pair.add_argument("code")
    pair.add_argument("--serial", help="device serial to report (default: random SIM-GW-xxxx)")

    run = sub.add_parser("run", help="catch up, then stream live readings")
    run.add_argument("--interval", type=int, default=300, help="seconds between live readings (default 300)")
    run.add_argument("--catch-up-days", type=int, default=30, help="how far back to fill gaps (default 30)")
    run.add_argument("--no-random-faults", action="store_true",
                     help="only faults you inject (clearer for a demo)")
    run.add_argument("--seed", type=int, help="random seed (default: different every run)")

    sub.add_parser("unpair", help="forget the device token")

    args = p.parse_args()
    try:
        if args.command == "pair":
            cmd_pair(args)
        elif args.command == "run":
            if args.interval < 5:
                raise GatewayError("--interval must be at least 5 seconds")
            cmd_run(args)
        else:
            STATE_FILE.unlink(missing_ok=True)
            print("Device token removed.")
    except GatewayError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
