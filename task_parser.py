import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright


async def click_all(page, selector):
    els = await page.query_selector_all(selector)
    for el in els:
        try:
            await el.click()
            await asyncio.sleep(0.15)
        except Exception:
            pass
    return len(els)


async def scrape_variant(page, url: str) -> dict:
    print(url)
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)

    is_self_checking = "self-checking" in url

    if is_self_checking:
        await page.wait_for_selector("div[class*='collapseContainer']", timeout=20000)
        await asyncio.sleep(2)

        n = await click_all(page, "div[class*='collapseContainer'] div[class*='collapseHeader']")
        print(f"  Opened blocks: {n}")
        await asyncio.sleep(1)

        btns = await page.query_selector_all("button span[class*='styles_text']")
        clicked = 0
        for btn in btns:
            try:
                if "Ответ и решение" in await btn.inner_text():
                    await btn.click()
                    await asyncio.sleep(0.15)
                    clicked += 1
            except Exception:
                pass
        print(f"  Opened solutions: {clicked}")

        n2 = await click_all(page, "div[class*='toEstimateExerciseCard'] div[class*='collapseHeader']")
        print(f"  Opened second parts: {n2}")

        await asyncio.sleep(3)

    else:
        await page.wait_for_selector("div[class*='exerciseCard']", timeout=20000)
        await asyncio.sleep(4)

    title = await page.evaluate("""
        () => {
            const el = document.querySelector("span[class*='styles_title']");
            return el ? el.innerText.trim() : "";
        }
    """)

    questions = await page.evaluate("""
        (isSelfChecking) => {

            function extractText(container) {
                if (!container) return "";
                const clone = container.cloneNode(true);
                clone.querySelectorAll("img.math, img.math-display").forEach(img => {
                    img.replaceWith(img.getAttribute("alt") || "");
                });
                return clone.innerText.replace(/\\s+/g, " ").trim();
            }

            function extractBlocks(root, selector) {
                const parts = [];
                root.querySelectorAll(selector).forEach(el => {
                    const text = extractText(el);
                    if (text) parts.push(text);
                });
                return parts.join(" ");
            }

            function getCollapseByLabel(card, label) {
                const collapses = card.querySelectorAll("div[class*='styles_collapse']");
                for (const c of collapses) {
                    const header = c.querySelector("div[class*='collapseHeader']");
                    if (header && header.innerText.includes(label)) return c;
                }
                return null;
            }

            const result = [];

            if (isSelfChecking) {

                const part1 = document.querySelectorAll("div[class*='collapseContainer']");
                part1.forEach((container, index) => {
                    const bodyEl = container.querySelector("div[id^='solve-variant-exercise']");
                    const exerciseId = bodyEl ? bodyEl.id.replace("solve-variant-exercise-", "") : null;

                    const modules = container.querySelectorAll("div[class*='latexModule']");
                    const questionText = modules[0] ? extractBlocks(modules[0], "p.noindent, p.indent, div.math-display") : "";
                    const solutionText = modules[1] ? extractBlocks(modules[1], "p.noindent, p.indent, div.math-display") : "";

                    const allInputs = container.querySelectorAll("label input");
                    let answer = "";
                    allInputs.forEach(inp => {
                        const v = inp.getAttribute("value") || "";
                        if (v !== "" && answer === "") answer = v;
                    });

                    result.push({
                        number: index + 1,
                        exercise_id: exerciseId,
                        text: questionText,
                        solution: solutionText,
                        answer: answer
                    });
                });

                const part2 = document.querySelectorAll("div[class*='toEstimateExerciseCard']");
                const offset = result.length;
                part2.forEach((card, index) => {
                    // exercise_id берём из серого span с # в заголовке карточки
                    const idSpan = card.querySelector("div[class*='exerciseCardHeader'] span[class*='textColor']");
                    const exerciseId = idSpan ? idSpan.innerText.replace("#", "").trim() : null;

                    const taskCollapse   = getCollapseByLabel(card, "Задание");
                    const solveCollapse  = getCollapseByLabel(card, "Ответ и решение");

                    const questionText = taskCollapse  ? extractBlocks(taskCollapse,  "p.noindent, p.indent, div.math-display") : "";
                    const solutionText = solveCollapse ? extractBlocks(solveCollapse, "p.noindent, p.indent, div.math-display") : "";

                    result.push({
                        number: offset + index + 1,
                        exercise_id: exerciseId,
                        text: questionText,
                        solution: solutionText
                    });
                });

            } else {
                const cards = document.querySelectorAll("div[class*='exerciseCard']");
                cards.forEach((card, index) => {
                    const bodyEl = card.querySelector("div[id^='solve-variant-exercise']");
                    const exerciseId = bodyEl ? bodyEl.id.replace("solve-variant-exercise-", "") : null;

                    const headerEl = card.querySelector("div[class*='exerciseBodyHeader']");
                    const headerText = headerEl ? headerEl.innerText.trim() : "";

                    const questionText = extractBlocks(card, "p.noindent");

                    result.push({
                        number: index + 1,
                        exercise_id: exerciseId,
                        header: headerText,
                        text: questionText
                    });
                });
            }

            return result;
        }
    """, is_self_checking)

    return {
        "url": url,
        "title": title,
        "format": "self-checking" if is_self_checking else "in-progress",
        "questions_count": len(questions),
        "questions": questions
    }


async def main():
    urls_file = Path(__file__).parent / "urls.txt"
    if urls_file.exists():
        urls = [line.strip() for line in urls_file.read_text().splitlines() if line.strip()]
        print(urls_file)
    else:
        urls = [
            "https://3.shkolkovo.online/solve-variant/hmNqDWKlxKNVTjbkpZNMWZR/self-checking"
        ]
        print("file not found")

    print(len(urls))
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.route("**/*.{png,jpg,jpeg,gif,woff,woff2}", lambda r: r.abort())

        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] parsing")
            try:
                data = await scrape_variant(page, url)
                results.append(data)
                print(f"'{data['title']}' [{data['format']}] — {data['questions_count']} questions")

                if data["questions"]:
                    q = data["questions"][0]
                    print(f"  q1: {q['text'][:120]}...")
                    if q.get("solution"):
                        print(f"  s1: {q['solution'][:120]}...")



            except Exception as e:
                results.append({"url": url, "error": str(e)})

        await browser.close()

    output_path = Path(__file__).parent / "result.json"
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nSaved to {output_path}")
    print(f"Saved vars: {len(results)}")
    total_q = sum(r.get("questions_count", 0) for r in results)
    print(f"Total questions: {total_q}")


if __name__ == "__main__":
    asyncio.run(main())