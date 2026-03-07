import { createClient } from "@libsql/client/web";

const globalForTurso = globalThis as unknown as {
  turso: ReturnType<typeof createClient> | undefined;
};

function createTursoClient() {
  return createClient({
    url: process.env.TURSO_DATABASE_URL!,
    authToken: process.env.TURSO_AUTH_TOKEN,
  });
}

export const turso = globalForTurso.turso ?? createTursoClient();

if (process.env.NODE_ENV !== "production") {
  globalForTurso.turso = turso;
}
