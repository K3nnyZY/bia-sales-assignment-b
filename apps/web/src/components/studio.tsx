"use client";

import Link from "next/link";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { studioRequest, type Principal } from "../lib/studio";

type Api = <T>(path: string, method?: string, body?: unknown) => Promise<T>;
type Session = {
  user: Principal | null;
  api: Api;
  login: (token: string) => Promise<void>;
  logout: () => void;
};
const StudioContext = createContext<Session | null>(null);

export function StudioProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState("");
  const [user, setUser] = useState<Principal | null>(null);
  const api: Api = useCallback(
    (path, method, body) => studioRequest(path, token, method, body),
    [token],
  );
  async function login(value: string) {
    const identity = await studioRequest<Principal>("/me", value);
    setToken(value);
    setUser(identity);
  }
  function logout() {
    setToken("");
    setUser(null);
  }
  return (
    <StudioContext.Provider value={{ user, api, login, logout }}>
      {children}
    </StudioContext.Provider>
  );
}

export function useStudio() {
  const session = useContext(StudioContext);
  if (!session) throw new Error("StudioProvider is required");
  return session;
}

export function useResource<T>(path: string | null) {
  const { api } = useStudio();
  const [result, setResult] = useState<{ path: string; data: T } | null>(null);
  const [error, setError] = useState<{ path: string; message: string } | null>(
    null,
  );
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    if (path)
      void api<T>(path)
        .then((data) => {
          if (active) {
            setResult({ path, data });
            setError(null);
          }
        })
        .catch((err: Error) => {
          if (active) setError({ path, message: err.message });
        });
    return () => {
      active = false;
    };
  }, [path, api, revision]);
  function refresh() {
    setResult(null);
    setError(null);
    setRevision((value) => value + 1);
  }
  return {
    data: result?.path === path ? result.data : null,
    error: error?.path === path ? error.message : null,
    refresh,
  };
}

export function SiteHeader() {
  return (
    <header>
      <Link className="brand" href="/agents">
        BIA<span>Agent Studio</span>
      </Link>
      <nav aria-label="Navegación principal">
        <Link href="/dashboard">Dashboard</Link>
        <Link href="/agents">Agentes</Link>
        <Link href="/models">Modelos</Link>
        <Link href="/tools">Herramientas</Link>
        <Link href="/knowledge">Conocimiento</Link>
        <Link href="/playground">Playground</Link>
        <Link href="/evaluations">Evaluaciones</Link>
        <Link href="/traces">Trazas</Link>
        <Link href="/">Infraestructura</Link>
      </nav>
    </header>
  );
}

function Login() {
  const { login } = useStudio();
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(token.trim());
      setToken("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel login">
      <p className="eyebrow">ACCESO AUTORIZADO</p>
      <h1>Entra al Studio.</h1>
      <p>
        Usa tu credencial privada proporcionada por el administrador. Los tokens
        demo del archivo .env solo funcionan en desarrollo local. La identidad,
        vigencia y permisos se verifican en el backend.
      </p>
      <form onSubmit={submit}>
        <label>
          Token de acceso
          <input
            type="password"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            required
            autoComplete="off"
          />
        </label>
        <button disabled={busy}>{busy ? "Verificando…" : "Entrar"}</button>
      </form>
      <p className="hint">
        El token se conserva solo en memoria. Al recargar tendrás que
        identificarte de nuevo.
      </p>
      <Feedback error={error} />
    </section>
  );
}

export function StudioShell({ children }: { children: ReactNode }) {
  const { user, logout } = useStudio();
  return (
    <main>
      <SiteHeader />
      {user ? (
        <>
          <div className="session">
            <span>
              {user.name} · {user.role}
            </span>
            <button className="secondary" onClick={logout}>
              Salir
            </button>
          </div>
          {children}
        </>
      ) : (
        <Login />
      )}
      <footer>BIA Agent Studio · Datos sintéticos · Acceso controlado</footer>
    </main>
  );
}

export function Feedback({
  error,
  success,
}: {
  error?: string | null;
  success?: string;
}) {
  return (
    <>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {success && (
        <p className="success" role="status">
          {success}
        </p>
      )}
    </>
  );
}
