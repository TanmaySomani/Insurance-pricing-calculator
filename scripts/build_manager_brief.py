"""Build exactly two manager-facing pages from committed, frozen evidence.

No training, download or scenario recalculation occurs here. PDF metadata is
deterministic; changing a source CSV creates a new evidence hash in the manifest.
Install requirements-report.txt alongside the normal environment to rebuild.
"""
import csv
import hashlib
import json
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import reportlab

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/pdf/pricing_manager_brief.pdf"
W, H = 595.276, 841.89  # A4, points
INK, MUTED, GREEN = map(HexColor, ["#26352F", "#56635C", "#365E4B"])
PAPER, PALE, LINE = map(HexColor, ["#FBFAF6", "#EDF1E9", "#D9DFD5"])
TAN = HexColor("#9F6745")
# Embed ReportLab's bundled sans fonts so readers do not need local fonts.
for name, filename in [("BriefSans", "Vera.ttf"), ("BriefSansBold", "VeraBd.ttf")]:
    pdfmetrics.registerFont(TTFont(name, str(Path(reportlab.__file__).parent / "fonts" / filename)))


def rows(path):
    with (ROOT / path).open(newline="") as stream:
        return list(csv.DictReader(stream))


def text(c, value, x, top, width, size=10, leading=14, font="Helvetica", color=INK, max_height=None):
    """Place wrapped text downwards; fail if its assigned box is too small."""
    font = {"Helvetica": "BriefSans", "Helvetica-Bold": "BriefSansBold"}.get(font, font)
    style = ParagraphStyle("block", fontName=font, fontSize=size, leading=leading, textColor=color)
    p = Paragraph(value, style)
    _, height = p.wrap(width, H)
    if max_height is not None and height > max_height:
        raise ValueError(f"Text exceeds assigned box: {value[:70]}")
    p.drawOn(c, x, top - height)
    return top - height


def chrome(c, page, label):
    c.setFillColor(PAPER); c.rect(0, 0, W, H, fill=1, stroke=0)
    text(c, "TANMAY SOMANI  /  MOTOR PRICING CASE STUDY", 42, H - 30, 440, 8, 10, color=MUTED)
    c.setStrokeColor(LINE); c.line(42, 52, W - 42, 52)
    text(c, "8 October 2026  |  Historical French liability, EUR  |  Illustrative analysis", 42, 40, 460, 7.5, 10, color=MUTED)
    text(c, f"{page} / 2", W - 70, 40, 40, 8, 10, color=MUTED)
    text(c, label.upper(), 42, H - 67, W - 84, 9, 12, color=GREEN)


def table(c, headers, data, x, top, widths, row_height=29, size=9):
    height = row_height * (len(data) + 1)
    c.setFillColor(PALE); c.rect(x, top - row_height, sum(widths), row_height, fill=1, stroke=0)
    for i, row in enumerate([headers] + data):
        left = x
        for value, width in zip(row, widths):
            text(c, str(value), left + 8, top - i * row_height - 8, width - 16,
                 size, 11, "Helvetica-Bold" if i == 0 else "Helvetica", max_height=row_height - 9)
            left += width
        c.setStrokeColor(LINE); c.line(x, top - (i + 1) * row_height, x + sum(widths), top - (i + 1) * row_height)
    return top - height


def main():
    paths = ["reports/dashboard/example_scenarios.csv", "reports/comparison/metrics.csv",
             "reports/comparison/paired_intervals.csv", "reports/dashboard/manifest.json",
             "reports/data_audit.json", "reports/comparison/selection.json"]
    cases = rows(paths[0]); base, low, medium, high, inflated = cases
    metrics = {r["model"]: r for r in rows(paths[1]) if r["split"] == "test"}
    g, b = metrics["glm"], metrics["boost"]
    assert int(b["policies"]) == 135246 and int(b["claims"]) == 5270
    assert float(low["rate_change"]) == .05 and float(high["elasticity"]) == 6
    intervals = {r["metric"]: r for r in rows(paths[2]) if r["split"] == "test" and r["model"] == "boost_minus_glm"}
    gain = (1 - float(b["pure_deviance"]) / float(g["pure_deviance"])) * 100
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT), pagesize=(W, H), invariant=1, pageCompression=1)
    c.setTitle("Motor pricing: contribution, retention and the decision")
    c.setAuthor("Tanmay Somani"); c.setSubject("Two-page pricing-manager brief, frozen Parts 1-5 case study")
    chrome(c, 1, "Business decision")
    text(c, "Can a rate increase pay<br/>for the renewals it loses?", 42, 746, 510, 28, 32, "Times-Roman")
    c.setFillColor(PALE); c.roundRect(42, 536, W - 84, 124, 5, fill=1, stroke=0)
    text(c, "RECOMMENDATION", 56, 644, 475, 9, 12, "Helvetica-Bold", GREEN)
    text(c, "Investigate a bounded +5% option; obtain actual premium and renewal evidence before a rollout.", 56, 624, 475, 13, 17, "Helvetica-Bold", max_height=38)
    text(c, f"At assumed elasticity 1.2, annual contribution increases by EUR {float(low['contribution_change_same_stress']) / 1e6:.2f}m, with {abs(float(low['retained_change'])):,.0f} fewer retained policies. At elasticity 6, contribution falls by EUR {abs(float(high['contribution_change_same_stress'])) / 1e6:.2f}m. These are conditional simulations, not achieved savings.", 56, 578, 475, 10, 14, max_height=42)
    text(c, "What the rate experiment shows", 42, 512, 510, 16, 20, "Times-Roman")
    data = []
    for label, r in [("No change", base), ("+5%; elasticity 1.2", low), ("+5%; elasticity 3", medium), ("+5%; elasticity 6", high)]:
        data.append([label, f"{float(r['retained']):,.0f}", f"{float(r['contribution']) / 1e6:.2f}", f"{float(r['contribution_change_same_stress']) / 1e6:+.2f}"])
    table(c, ["Rate / response", "Retained", "Contribution", "Change"], data, 42, 481, [195, 100, 112, 104], size=9)
    text(c, "Contribution and change: EUR millions. Retained volume: expected policies, rounded.", 42, 325, 510, 8, 11, color=MUTED)
    text(c, "The profit benefit depends on price response", 42, 301, 510, 14, 18, "Times-Roman")
    zero, scale = 297, 125
    c.setStrokeColor(LINE); c.line(zero, 210, zero, 272)
    for label, r, y in [("Elasticity 1.2", low, 249), ("Elasticity 6", high, 218)]:
        delta = float(r["contribution_change_same_stress"]) / 1e6
        text(c, label, 48, y + 10, 120, 9, 12)
        c.setFillColor(GREEN if delta >= 0 else TAN)
        c.rect(min(zero, zero + delta * scale), y, abs(delta) * scale, 14, fill=1, stroke=0)
        text(c, f"{delta:+.2f}m", 450, y + 12, 60, 10, 12, "Helvetica-Bold")
    text(c, "Assumed annual renewal economics", 42, 185, 510, 12, 16, "Helvetica-Bold")
    text(c, "135,246 policies; one renewal opportunity each; 85% baseline retention; boosting claims model; fixed GLM synthetic price anchor. Expenses: 25% of premium plus EUR 30 per retained policy. Price margin: 10%; no inflation in the table. Price = (GLM annual model loss + EUR 30) / 0.65.", 42, 163, 511, 9, 12, max_height=48)
    text(c, f"With 10% claims inflation, the +5% case contributes EUR {float(inflated['contribution']) / 1e6:.2f}m. Its +EUR {float(inflated['contribution_change_same_stress']) / 1e6:.2f}m rate benefit compares with a baseline under the same inflation. Current premiums and observed renewals are unavailable; response and prices are assumed.", 42, 103, 511, 8.5, 11, color=MUTED, max_height=44)
    c.showPage()

    chrome(c, 2, "Evidence, judgement and next action")
    text(c, "Better risk differentiation.<br/>A measured path to action.", 42, 746, 510, 27, 31, "Times-Roman")
    text(c, "Evidence from a frozen holdout", 42, 667, 510, 15, 19, "Times-Roman")
    table(c, ["Historical test measure", "GLM", "Boosting"], [
        ["Prediction error: lower is better", f"{float(g['pure_deviance']):.2f}", f"{float(b['pure_deviance']):.2f}"],
        ["Risk ranking (Gini): higher is better", f"{float(g['raw_gini']):.3f}", f"{float(b['raw_gini']):.3f}"],
        ["Actual / expected cost: target 1", f"{float(g['pure_premium_AE']):.3f}", f"{float(b['pure_premium_AE']):.3f}"],
    ], 42, 636, [323, 94, 94], size=9)
    p = intervals["pure_deviance"]
    text(c, f"Boosting reduces recorded-cost prediction error by {gain:.2f}%. The paired 95% sampling range for its error difference is {float(p['lower_95']):.2f} to {float(p['upper_95']):.2f}, favouring boosting. Gini improvement is supported; top-decile lift improvement remains uncertain. Error uses exposure-weighted Tweedie deviance (power 1.5).", 42, 505, 511, 9, 12, max_height=48)
    text(c, "How the model was built", 42, 447, 510, 12, 16, "Helvetica-Bold")
    text(c, "Public freMTPL2 data: 678,013 policies and 26,444 linked claims. Poisson GLM predicts annual claim frequency using exposure; Gamma GLM predicts individual claim size. Their product gives annual recorded loss cost. Boosting models the same components with nonlinear effects. Training, selection and final reporting use separate policy splits (60% / 20% / 20%); claims stay with their policy.", 42, 425, 511, 9, 12, max_height=48)
    text(c, "Model choice and review effort", 42, 365, 510, 12, 16, "Helvetica-Bold")
    text(c, "Use boosting for illustrative scenario exploration and retain GLM as the transparent benchmark. GLM factors are easier to explain; boosting improves measured fit but needs more stability and explanation review. Familiarity does not establish regulatory acceptance for either model. This project has no production or regulatory approval.", 42, 343, 511, 9, 12, max_height=36)
    text(c, "What limits the decision", 42, 294, 510, 12, 16, "Helvetica-Bold")
    text(c, "9,116 policies report claims with no cost record; those are not established zero losses. The largest 1% of linked claims account for about 38% of cost. Incomplete development, future drift and fitting uncertainty are outside the reported sampling intervals. Age 75+ GLM actual/expected reverses from about 1.67 on validation to 0.70 on test: do not turn an isolated segment ratio into a rate rule.", 42, 272, 511, 9, 12, max_height=48)
    text(c, "Proposed next decision", 42, 212, 510, 12, 16, "Helvetica-Bold")
    text(c, "Obtain developed claims, current premiums, renewal outcomes and expense economics. Validate over time and customers; review permitted variables, fairness and stability. Only then assess a bounded pilot with agreed contribution and retention limits. Monitor actual vs expected claims and renewal response, with a documented rollback decision.", 42, 190, 511, 9, 12, max_height=48)
    text(c, "Dashboard: change a rate, stress elasticity, compare models at one price anchor, and save the scenario. Contribution excludes capital, reinsurance, tax and investment income. Historical French EUR results do not establish current Australian prices.", 42, 132, 511, 8.5, 11, color=MUTED, max_height=33)
    text(c, '<link href="https://github.com/TanmaySomani/Insurance-pricing-calculator" color="#365E4B">Source, dashboard and full evidence: github.com/TanmaySomani/Insurance-pricing-calculator</link><br/>Sources: OpenML 41214 / 41215 v1; committed metrics, paired intervals and example scenarios. Test: 135,246 policies / 5,270 linked claims; 250 paired policy-bootstrap draws, fixed predictions.', 42, 87, 511, 7, 9, color=MUTED, max_height=27)
    c.save()
    manifest = {"pdf": str(OUT.relative_to(ROOT)), "expected_pages": 2,
                "sources_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
                "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "pdf_sha256": hashlib.sha256(OUT.read_bytes()).hexdigest(), "reportlab_version": __import__("reportlab").Version}
    dest = ROOT / "reports/handover"; dest.mkdir(parents=True, exist_ok=True)
    (dest / "brief_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(OUT)


if __name__ == "__main__":
    main()
