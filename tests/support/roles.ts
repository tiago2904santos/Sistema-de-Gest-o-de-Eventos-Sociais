/** Usuários de papel criados pelo seed (agent_lab/seed.py → PAPEIS). */
export const LAB_PASSWORD = process.env.LAB_PASSWORD ?? "Lab@2026!seguro";

export const ROLES = {
  admin: "lab.admin",
  gestorDg: "lab.gestor_dg",
  administrador: "lab.administrador",
  solicitante: "lab.solicitante",
  viagensGestor: "lab.viagens_gestor",
  viagensOperador: "lab.viagens_operador",
  viagensLeitor: "lab.viagens_leitor",
  ascom: "lab.ascom",
  semModulo: "lab.sem_modulo",
} as const;

export type Role = keyof typeof ROLES;

export const storageStatePath = (role: Role) => `.lab/auth/${role}.json`;
