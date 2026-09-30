import { expect, test } from "@playwright/test";

test("English candidate story reaches human review without an invented score", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Show us how you act." })).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: /Try an example response/ }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: /Hear both sides/ }).click();
  await page.getByPlaceholder("I would first... Then...").fill("I would agree on a task owner and check progress that evening.");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Your impact, in your words" })).toBeVisible();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Open reviewer view" }).click();
  await expect(page.getByRole("heading", { name: "История кандидата на языке оригинала" })).toBeVisible();
  await expect(page.getByText("Ситуационная мини-сцена используется как дополнительный материал", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Сохранить решение" }).click();
  await expect(page.getByRole("alert").getByText("Добавьте короткое объяснение решения", { exact: false })).toBeVisible();
  await page.getByPlaceholder("Коротко объясните решение комиссии").fill("Нужно уточнить конкретную роль и проверить результат истории.");
  await page.getByRole("button", { name: "Сохранить решение" }).click();
  await expect(page.getByText("Нужно уточнить конкретную роль и проверить результат истории.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Скачать отчёт JSON" })).toHaveCount(0);
});

test("existing HTTPS video is handed off without uploading or scoring", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Record video/ }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByPlaceholder("https://...").fill("https://example.org/fictional-video");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: /Ask another team member/ }).click();
  await page.getByPlaceholder("I would first... Then...").fill("I would ask for a short mediation, then split the remaining work.");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Open reviewer view" }).click();
  await expect(page.getByRole("link", { name: /Открыть исходное видео/ })).toHaveAttribute("href", "https://example.org/fictional-video");
  await expect(page.getByText("Исходная запись доступна комиссии", { exact: false })).toBeVisible();
});

test("candidate page fits a narrow phone viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await expect(page.getByRole("button", { name: /Record video/ })).toBeVisible();
});

test("Russian text gets experimental analysis and priority route needs evidence", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "RU", exact: true }).click();
  await page.getByRole("button", { name: "Продолжить" }).click();
  await page.getByRole("button", { name: /Посмотреть пример ответа/ }).click();
  await page.getByRole("button", { name: "Продолжить" }).click();
  await page.getByRole("button", { name: /Выслушаю обоих/ }).click();
  await page.getByPlaceholder("Сначала я... Затем...").fill("Сначала выслушаю обоих, затем распределю задачи на оставшийся день.");
  await page.getByRole("button", { name: "Продолжить" }).click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Открыть кабинет комиссии" }).click();
  await expect(page.getByRole("heading", { name: "Структура ответа" })).toBeVisible();
  await page.getByLabel("Следующий шаг").selectOption("priority_interview");
  await page.getByPlaceholder("Коротко объясните решение комиссии").fill("Кандидат описал конкретные действия и измеримый результат.");
  await page.getByRole("button", { name: "Сохранить решение" }).click();
  await expect(page.getByText("Чтобы пригласить кандидата в первую очередь", { exact: false }).first()).toBeVisible();
  await page.getByPlaceholder("Цитата или наблюдение, на котором основано решение").fill("составил общее расписание и распределил небольшие роли");
  await page.getByRole("button", { name: "Сохранить решение" }).click();
  await expect(page.getByText("Кандидат описал конкретные действия и измеримый результат.")).toBeVisible();
});

test("voice recording is stored in the local pilot and reaches the reviewer", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Speak/ }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: /Start recording/ }).click();
  await expect(page.getByRole("button", { name: /Stop recording/ })).toBeVisible();
  await page.waitForTimeout(700);
  await page.getByRole("button", { name: /Stop recording/ }).click();
  await expect(page.locator("audio")).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: /Pick a plan yourself/ }).click();
  await page.getByPlaceholder("I would first... Then...").fill("I would explain the deadline and then listen to objections.");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Open reviewer view" }).click();
  await expect(page.locator(".handoff-media audio")).toBeVisible();
  await expect(page.getByText("Ответ направлен на проверку комиссии", { exact: false })).toBeVisible();
  await expect(page.getByText(/сохранено под кодом QDM-/)).toBeVisible();
});

test("video can be recorded locally without an upload", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Record video/ }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: /Start recording/ }).click();
  await page.waitForTimeout(700);
  await page.getByRole("button", { name: /Stop recording/ }).click();
  await expect(page.locator("video")).toBeVisible();
  await expect(page.locator("video")).toHaveAttribute("src", /^blob:/);
});

test("provisional nine-block framework is visible and clearly labelled", async ({ page }) => {
  await page.goto("/?view=methodology");
  await expect(page.getByRole("heading", { name: "Карта компетенций", exact: true })).toBeVisible();
  await expect(page.getByText("ДЛЯ СОГЛАСОВАНИЯ")).toBeVisible();
  await expect(page.locator(".qef-item")).toHaveCount(9);
  await expect(page.getByText("Ценности в действии", { exact: true })).toBeVisible();
  await expect(page.getByText("Развитие через трудности", { exact: true }).first()).toBeVisible();
});
