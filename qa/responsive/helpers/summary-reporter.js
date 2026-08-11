const fs = require("fs");
const path = require("path");

/**
 * Playwright reporter → reports/responsive-summary.json + console digest.
 */
class SummaryReporter {
  constructor() {
    this.results = [];
  }

  onTestEnd(test, result) {
    const ann = (result.annotations || []).find((a) => a.type === "responsive-qa");
    if (!ann || !ann.description) return;
    try {
      this.results.push(JSON.parse(ann.description));
    } catch {
      /* ignore */
    }
  }

  onEnd() {
    const reportDir = path.join(__dirname, "..", "reports");
    fs.mkdirSync(reportDir, { recursive: true });

    let errors = 0;
    let warnings = 0;
    const scored = this.results.map((r) => {
      errors += r.errorCount || 0;
      warnings += r.warningCount || 0;
      return {
        ...r,
        score: (r.errorCount || 0) * 10 + (r.warningCount || 0),
      };
    });

    scored.sort((a, b) => b.score - a.score);

    const summary = {
      generatedAt: new Date().toISOString(),
      testedRoutes: new Set(scored.map((r) => r.route)).size,
      viewports: new Set(scored.map((r) => r.viewport)).size,
      totalChecks: scored.length,
      errors,
      warnings,
      results: scored.map(({ score, ...rest }) => rest),
      mostProblematic: scored.slice(0, 10).map((r) => ({
        route: r.route,
        viewport: r.viewport,
        errorCount: r.errorCount,
        warningCount: r.warningCount,
      })),
    };

    const outPath = path.join(reportDir, "responsive-summary.json");
    fs.writeFileSync(outPath, JSON.stringify(summary, null, 2), "utf8");

    console.log("\n==============================");
    console.log("RESPONSIVE QA");
    console.log("==============================");
    console.log(`Tested routes: ${summary.testedRoutes}`);
    console.log(`Viewports: ${summary.viewports}`);
    console.log(`Total checks: ${summary.totalChecks}`);
    console.log("");
    console.log(`Errors: ${summary.errors}`);
    console.log(`Warnings: ${summary.warnings}`);
    console.log("");
    console.log("Most problematic:");
    if (!summary.mostProblematic.length) {
      console.log("(none)");
    } else {
      summary.mostProblematic.slice(0, 8).forEach((m, i) => {
        console.log(
          `${i + 1}. ${m.route} — ${m.viewport} (E:${m.errorCount} W:${m.warningCount})`
        );
      });
    }
    console.log(`\nJSON: ${outPath}`);
    console.log("==============================\n");
  }
}

module.exports = SummaryReporter;
