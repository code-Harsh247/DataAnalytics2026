"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";

export default function LoginPage() {
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [signupSuccess, setSignupSuccess] = useState(false);
  const { session, signIn, signUp } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (session) router.replace("/");
  }, [session, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const result = mode === "signin" ? await signIn(email, password) : await signUp(email, password);
    setLoading(false);
    if (result.error) {
      setError(result.error);
    } else if (mode === "signup") {
      // Supabase requires email confirmation by default -- no session yet.
      setSignupSuccess(true);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-bold text-gray-900">Solar Plant Manager</h1>
          <p className="text-sm text-gray-500">
            Know your plant&apos;s health before it costs you money.
          </p>
        </div>

        <div className="bg-white rounded-lg border shadow-sm p-6">
          {signupSuccess ? (
            <div className="text-center space-y-3">
              <p className="text-sm text-gray-700">
                Check <span className="font-medium">{email}</span> for a confirmation link, then
                sign in below.
              </p>
              <button
                type="button"
                onClick={() => {
                  setSignupSuccess(false);
                  setMode("signin");
                }}
                className="text-sm text-blue-600 hover:underline"
              >
                Back to sign in
              </button>
            </div>
          ) : (
            <>
              <div className="flex mb-4 rounded overflow-hidden border">
                <button
                  type="button"
                  onClick={() => setMode("signin")}
                  className={`flex-1 text-sm py-2 ${
                    mode === "signin" ? "bg-blue-600 text-white" : "bg-white text-gray-600"
                  }`}
                >
                  Sign in
                </button>
                <button
                  type="button"
                  onClick={() => setMode("signup")}
                  className={`flex-1 text-sm py-2 ${
                    mode === "signup" ? "bg-blue-600 text-white" : "bg-white text-gray-600"
                  }`}
                >
                  Sign up
                </button>
              </div>

              <form onSubmit={handleSubmit} className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Email</label>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full border rounded px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Password</label>
                  <input
                    type="password"
                    required
                    minLength={6}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full border rounded px-3 py-2 text-sm"
                  />
                </div>

                {error && <p className="text-sm text-red-600">{error}</p>}

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full bg-blue-600 text-white text-sm font-medium py-2 rounded hover:bg-blue-700 disabled:opacity-50"
                >
                  {loading ? "Please wait…" : mode === "signin" ? "Sign in" : "Create account"}
                </button>
              </form>
            </>
          )}
        </div>

        <p className="text-xs text-gray-400 text-center">
          Demo product — data shown is from a real historical dataset (two Indian solar plants),
          not a live feed.
        </p>
      </div>
    </div>
  );
}
