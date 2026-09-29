import { test, expect } from "../support/lab";
import { LAB_PASSWORD, ROLES } from "../support/roles";

test("login com credencial errada mostra erro e não entra", async ({ page }) => {
  await page.goto("/conta/entrar/");
  await page.getByLabel("Usuário").fill(ROLES.admin);
  await page.getByLabel("Senha", { exact: true }).fill("senha-errada");
  await page.locator("form button[type=submit]").click();
  await expect(page).toHaveURL(/\/conta\/entrar\//);
  await expect(page.locator(".form-erro, .errorlist, [role=alert], .aviso").first()).toBeVisible();
});

test("login → hub → logout", async ({ page }) => {
  await page.goto("/conta/entrar/");
  await page.getByLabel("Usuário").fill(ROLES.viagensGestor);
  await page.getByLabel("Senha", { exact: true }).fill(LAB_PASSWORD);
  await page.locator("form button[type=submit]").click();
  await expect(page).not.toHaveURL(/entrar/);
  await expect(page.getByRole("link", { name: /viagens/i }).first()).toBeVisible();
});

test("mostrar/ocultar senha alterna o tipo do campo", async ({ page }) => {
  await page.goto("/conta/entrar/");
  const senha = page.getByLabel("Senha", { exact: true });
  await senha.fill("abc");
  await page.getByRole("button", { name: "Mostrar senha" }).click();
  await expect(senha).toHaveAttribute("type", "text");
});

test("usuário com troca obrigatória é levado a alterar a senha", async ({ page }) => {
  await page.goto("/conta/entrar/");
  await page.getByLabel("Usuário").fill("lab.troca_senha");
  await page.getByLabel("Senha", { exact: true }).fill(LAB_PASSWORD);
  await page.locator("form button[type=submit]").click();
  await page.goto("/");
  await expect(page).toHaveURL(/alterar-senha/);
});
