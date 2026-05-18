"""
semisector/email_reporter.py
─────────────────────────────
EmailReporter — sends a professionally formatted HTML email report
via Office 365 / Outlook SMTP.

The email contains:
  Section 1 — Executive Summary (sector verdict, top picks)
  Section 2 — Ranked Opportunity Table (all tickers scored)
  Section 3 — Detailed Analysis (per-ticker strategy & rationale)
  Section 4 — Backtest Results (if available)
  Section 5 — Weight Optimization Results (if available)
  Section 6 — Disclaimer

Configuration
─────────────
Set these environment variables (or pass directly to EmailReporter):

  SEMISECTOR_EMAIL_FROM     your.email@outlook.com
  SEMISECTOR_EMAIL_TO       recipient@example.com  (comma-separated for multiple)
  SEMISECTOR_EMAIL_PASSWORD  your Office 365 password or app password

Or create a .env file in the project root (never commit this to GitHub):
  SEMISECTOR_EMAIL_FROM=your.email@outlook.com
  SEMISECTOR_EMAIL_TO=recipient@example.com
  SEMISECTOR_EMAIL_PASSWORD=yourpassword
"""

from __future__ import annotations

import os
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from typing import Optional

from semisector.models import AnalysisResult


# Gmail SMTP settings
O365_HOST = "smtp.gmail.com"
O365_PORT = 587


class EmailReporter:
    """
    Builds and sends a professional HTML email report via Office 365.

    Usage:
        reporter = EmailReporter(
            from_addr  = "you@outlook.com",
            to_addrs   = ["recipient@example.com"],
            password   = "your_password",
        )
        reporter.send(results, backtest_report=None, opt_result=None)
    """

    def __init__(
        self,
        from_addr:  Optional[str]       = None,
        to_addrs:   Optional[list[str]] = None,
        password:   Optional[str]       = None,
        smtp_host:  str                 = O365_HOST,
        smtp_port:  int                 = O365_PORT,
    ) -> None:
        self.from_addr = from_addr or os.getenv("SEMISECTOR_EMAIL_FROM", "")
        raw_to         = to_addrs  or os.getenv("SEMISECTOR_EMAIL_TO", "").split(",")
        self.to_addrs  = [a.strip() for a in raw_to if a.strip()]
        self.password  = password  or os.getenv("SEMISECTOR_EMAIL_PASSWORD", "")
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port

    # ── Public API ────────────────────────────────────────────────────────────

    def send(
        self,
        results:          list[AnalysisResult],
        backtest_report   = None,
        opt_result        = None,
    ) -> bool:
        """
        Build the HTML email and send it via Office 365.
        Returns True on success, False on failure.
        """
        if not self._validate_config():
            return False

        subject = (f"NaYa Fintech | Semiconductor Sector Report | "
                   f"{datetime.today():%B %d, %Y}")
        html    = self._build_html(results, backtest_report, opt_result)
        msg     = self._build_message(subject, html)

        try:
            context = ssl.create_default_context()
            # Try SMTP_SSL (port 465) first — works for Hotmail/personal Microsoft accounts
            try:
                with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
                    server.ehlo()
                    server.login(self.from_addr, self.password)
                    server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
            except Exception:
                # Fallback: STARTTLS (port 587) — works for Office 365 corporate accounts
                with smtplib.SMTP("smtp.gmail.com", 587) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                    server.login(self.from_addr, self.password)
                    server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
            print(f"  ✅ Email sent to {', '.join(self.to_addrs)}")
            return True
        except smtplib.SMTPAuthenticationError:
            print("  ❌ Email failed: Authentication error. "
                  "Check your email and password / app password.")
        except smtplib.SMTPException as e:
            print(f"  ❌ Email failed: {e}")
        except Exception as e:
            print(f"  ❌ Email failed (unexpected): {e}")
        return False

    def preview_html(self, results: list[AnalysisResult],
                     backtest_report=None, opt_result=None) -> str:
        """Return the HTML string without sending — useful for testing."""
        return self._build_html(results, backtest_report, opt_result)

    # ── Config validation ─────────────────────────────────────────────────────

    def _validate_config(self) -> bool:
        issues = []
        if not self.from_addr: issues.append("SEMISECTOR_EMAIL_FROM not set")
        if not self.to_addrs:  issues.append("SEMISECTOR_EMAIL_TO not set")
        if not self.password:  issues.append("SEMISECTOR_EMAIL_PASSWORD not set")
        if issues:
            for i in issues:
                print(f"  ⚠  Email config: {i}")
            return False
        return True

    # ── Message builder ───────────────────────────────────────────────────────

    def _build_message(self, subject: str, html: str) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = self.from_addr
        msg["To"]      = ", ".join(self.to_addrs)
        msg.attach(MIMEText(html, "html"))
        return msg

    # ── HTML builder ─────────────────────────────────────────────────────────

    def _build_html(self, results: list[AnalysisResult],
                    backtest_report, opt_result) -> str:
        sorted_r    = sorted(results, key=lambda r: r.score, reverse=True)
        avg_score   = sum(r.score for r in results) / len(results) if results else 0
        top3        = sorted_r[:3]
        overbought  = [r.ticker for r in results if r.ind.rsi > 68]
        high_opp    = [r.ticker for r in results if r.score >= 70]

        # Sector verdict
        if avg_score >= 65:
            verdict_color = "#16a34a"
            verdict_text  = "✅ SECTOR STILL HAS LEGS — Strong entry opportunities remain"
            verdict_sub   = "Multiple tickers showing valid setups. New money can be deployed."
        elif avg_score >= 45:
            verdict_color = "#d97706"
            verdict_text  = "⚡ MIXED PICTURE — Selective opportunity remains"
            verdict_sub   = "Sector has run hard. Use DCA or limit orders rather than lump-sum."
        else:
            verdict_color = "#dc2626"
            verdict_text  = "⚠️ CAUTION — Broad sector extended or losing momentum"
            verdict_sub   = "Wait for RSI reset below 55 before deploying new capital."

        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NaYa Fintech Semiconductor Report</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background:#f8fafc;
          color:#1e293b; margin:0; padding:20px; }}
  .container {{ max-width:900px; margin:0 auto; background:#fff;
                border-radius:12px; box-shadow:0 4px 24px rgba(0,0,0,0.08); overflow:hidden; }}
  .header {{ background:linear-gradient(135deg,#1e293b 0%,#334155 100%);
             color:#fff; padding:32px 40px; }}
  .header h1 {{ margin:0 0 4px; font-size:24px; font-weight:700; }}
  .header p  {{ margin:0; opacity:0.75; font-size:14px; }}
  .badge {{ display:inline-block; background:rgba(255,255,255,0.15);
            border-radius:20px; padding:4px 12px; font-size:12px;
            margin-top:10px; }}
  .section {{ padding:28px 40px; border-bottom:1px solid #f1f5f9; }}
  .section:last-child {{ border-bottom:none; }}
  .section-title {{ font-size:16px; font-weight:700; color:#334155;
                    margin:0 0 16px; text-transform:uppercase;
                    letter-spacing:0.05em; }}
  .verdict-box {{ background:{verdict_color}15; border-left:4px solid {verdict_color};
                  border-radius:8px; padding:16px 20px; margin-bottom:16px; }}
  .verdict-box h3 {{ margin:0 0 4px; color:{verdict_color}; font-size:15px; }}
  .verdict-box p  {{ margin:0; color:#475569; font-size:13px; }}
  .stat-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px;
                margin-bottom:16px; }}
  .stat-card {{ background:#f8fafc; border-radius:8px; padding:14px 16px;
                text-align:center; border:1px solid #e2e8f0; }}
  .stat-card .val {{ font-size:22px; font-weight:700; color:#1e293b; }}
  .stat-card .lbl {{ font-size:11px; color:#94a3b8; text-transform:uppercase;
                     letter-spacing:0.05em; margin-top:2px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ background:#f1f5f9; color:#64748b; font-weight:600; padding:10px 12px;
        text-align:left; font-size:11px; text-transform:uppercase;
        letter-spacing:0.05em; }}
  td {{ padding:10px 12px; border-bottom:1px solid #f1f5f9; }}
  tr:last-child td {{ border-bottom:none; }}
  tr:hover td {{ background:#f8fafc; }}
  .score-high  {{ color:#16a34a; font-weight:700; }}
  .score-med   {{ color:#d97706; font-weight:700; }}
  .score-low   {{ color:#dc2626; font-weight:700; }}
  .ret-pos     {{ color:#16a34a; }}
  .ret-neg     {{ color:#dc2626; }}
  .ticker-card {{ background:#f8fafc; border-radius:10px; padding:20px;
                  margin-bottom:16px; border:1px solid #e2e8f0; }}
  .ticker-card h3 {{ margin:0 0 12px; font-size:15px; color:#1e293b; }}
  .ticker-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; }}
  .ticker-item {{ font-size:12px; }}
  .ticker-item .lbl {{ color:#94a3b8; }}
  .ticker-item .val {{ color:#1e293b; font-weight:600; }}
  .strategy-box {{ background:#eff6ff; border-radius:6px; padding:10px 14px;
                   margin-top:10px; border-left:3px solid #3b82f6; }}
  .strategy-box .strat-name {{ font-weight:700; color:#1d4ed8; font-size:13px; }}
  .strategy-box .strat-action {{ font-size:12px; color:#374151; margin-top:4px; }}
  .strategy-box .strat-tips {{ font-size:11px; color:#6b7280; margin-top:6px;
                                padding-left:14px; }}
  .chip {{ display:inline-block; padding:2px 8px; border-radius:10px;
           font-size:11px; font-weight:600; }}
  .chip-green  {{ background:#dcfce7; color:#16a34a; }}
  .chip-yellow {{ background:#fef9c3; color:#ca8a04; }}
  .chip-red    {{ background:#fee2e2; color:#dc2626; }}
  .model-box {{ background:#f0fdf4; border-radius:8px; padding:14px 16px;
                margin-bottom:10px; border:1px solid #bbf7d0; }}
  .model-box.winner {{ border-color:#16a34a; background:#dcfce7; }}
  .footer {{ background:#f8fafc; padding:20px 40px; text-align:center;
             font-size:11px; color:#94a3b8; }}
</style>
</head>
<body>
<div class="container">

  <!-- HEADER -->
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#1e293b;"><tr><td style="padding:32px 40px;"><p style="margin:0 0 4px;font-size:11px;color:rgba(255,255,255,0.55);font-family:Arial,sans-serif;">NaYa Fintech | Technofunctional Consulting | CFA, FRM Expertise</p><h1 style="margin:8px 0 6px;font-size:24px;font-weight:700;color:#ffffff;font-family:Arial,sans-serif;">Semiconductor Sector Intelligence Report</h1><p style="margin:0 0 16px;font-size:13px;color:rgba(255,255,255,0.7);font-family:Arial,sans-serif;">Daily Market Analysis - AI-Assisted Research</p></td></tr></table><div style="display:none">
    <h1>Semiconductor Sector Intelligence Report</h1>
    <p>NaYa Fintech | Technofunctional Consulting | Financial Services Solutions</p>
    <div class="badge"> {datetime.today():%B %d, %Y  %I:%M %p}</div>
    <div class="badge"> Powered by Claude AI</div>
  </div>

  <!-- SECTION 1: EXECUTIVE SUMMARY -->
  <div class="section">
    <div class="section-title">Executive Summary</div>

    <div class="verdict-box">
      <h3>{verdict_text}</h3>
      <p>{verdict_sub}</p>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="val">{avg_score:.0f}/100</div>
        <div class="lbl">Avg Opportunity Score</div>
      </div>
      <div class="stat-card">
        <div class="val">{len(high_opp)}/{len(results)}</div>
        <div class="lbl">High-Opportunity Tickers</div>
      </div>
      <div class="stat-card">
        <div class="val">{len(overbought)}</div>
        <div class="lbl">Potentially Overbought</div>
      </div>
    </div>

    <p style="font-size:13px;color:#475569;margin:0;">
      <strong>Top picks today:</strong>
      {', '.join(f'<strong>{r.ticker}</strong> ({r.score})' for r in top3)}
      &nbsp;|&nbsp;
      <strong>Overbought (caution):</strong>
      {', '.join(overbought) if overbought else 'None'}
    </p>
  </div>

  <!-- SECTION 2: RANKED TABLE -->
  <div class="section">
    <div class="section-title">Ranked Opportunity Table</div>
    <table>
      <thead>
        <tr>
          <th>Rank</th><th>Ticker</th><th>Price</th><th>Score</th>
          <th>RSI</th><th>ADX</th><th>1M Return</th><th>3M Return</th>
          <th>vs SPY</th><th>Trend</th><th>Top Strategy</th>
        </tr>
      </thead>
      <tbody>
        {self._ranked_rows(sorted_r)}
      </tbody>
    </table>
  </div>

  <!-- SECTION 3: DETAILED ANALYSIS -->
  <div class="section">
    <div class="section-title">Detailed Ticker Analysis</div>
    {self._detail_cards(sorted_r)}
  </div>

  <!-- SECTION 4: BACKTEST RESULTS -->
  {self._backtest_section(backtest_report)}

  <!-- SECTION 5: WEIGHT OPTIMIZATION -->
  {self._optimization_section(opt_result)}

  <!-- FOOTER / DISCLAIMER -->
  <div class="footer">
    <p><strong>⚠️ Disclaimer:</strong> This report is generated by NaYa Fintech's
    automated semiconductor sector analyzer for <em>educational and research purposes only</em>.
    It does NOT constitute financial advice. All analysis is based on technical indicators
    and historical data. Past performance does not guarantee future results.
    Please consult a licensed financial advisor before making any investment decisions.</p>
    <p style="margin-top:8px;">
      Code developed with assistance from
      <a href="https://www.anthropic.com/claude" style="color:#6366f1;">Claude AI</a>
      by Anthropic &nbsp;|&nbsp;
      <a href="https://github.com/ybhambha/NaYa_Fintech"
         style="color:#6366f1;">github.com/ybhambha/NaYa_Fintech</a>
    </p>
  </div>

</div>
</body>
</html>"""
        return html

    # ── HTML sub-builders ─────────────────────────────────────────────────────

    def _score_class(self, score: float) -> str:
        if score >= 70: return "score-high"
        if score >= 45: return "score-med"
        return "score-low"

    def _ret_fmt(self, v) -> str:
        if v is None: return "<span style='color:#94a3b8'>N/A</span>"
        cls = "ret-pos" if v >= 0 else "ret-neg"
        return f"<span class='{cls}'>{v:+.1f}%</span>"

    def _chip(self, score: float) -> str:
        if score >= 70: return f"<span class='chip chip-green'>{score:.0f}</span>"
        if score >= 45: return f"<span class='chip chip-yellow'>{score:.0f}</span>"
        return f"<span class='chip chip-red'>{score:.0f}</span>"

    def _ranked_rows(self, results: list[AnalysisResult]) -> str:
        rows = ""
        for i, r in enumerate(results, 1):
            top = r.cash_strats[0].name if r.cash_strats else "—"
            # Strip emoji for cleaner table
            top_clean = top[2:].strip() if len(top) > 2 else top
            rows += f"""
        <tr>
          <td style="font-weight:600;color:#94a3b8;">{i}</td>
          <td style="font-weight:700;">{r.ticker}</td>
          <td>${r.price:,.2f}</td>
          <td class="{self._score_class(r.score)}">{r.score}</td>
          <td>{r.ind.rsi:.1f}</td>
          <td>{r.ind.adx:.1f}</td>
          <td>{self._ret_fmt(r.ind.ret_1m)}</td>
          <td>{self._ret_fmt(r.ind.ret_3m)}</td>
          <td>{self._ret_fmt(r.rs_vs_spy)}</td>
          <td style="font-size:11px;">{r.ind.trend}</td>
          <td style="font-size:11px;">{top_clean[:40]}</td>
        </tr>"""
        return rows

    def _detail_cards(self, results: list[AnalysisResult]) -> str:
        cards = ""
        for r in results:
            ind    = r.ind
            td     = r.td
            strats = r.cash_strats[:2]   # top 2 strategies

            # Score badge
            badge = self._chip(r.score)

            # Fundamentals
            pe   = f"{td.pe_fwd:.1f}x"   if td.pe_fwd   else "N/A"
            peg  = f"{td.peg:.2f}x"      if td.peg      else "N/A"
            mc   = f"${td.market_cap/1e9:.0f}B" if td.market_cap else "N/A"
            tgt  = (f"${td.analyst_target:,.2f} "
                    f"({(td.analyst_target/ind.price-1)*100:+.0f}%)"
                    if td.analyst_target and ind.price else "N/A")

            # Strategy boxes
            strat_html = ""
            for s in strats:
                tips_html = "".join(f"<li>{t}</li>" for t in s.tips[:3])
                strat_html += f"""
              <div class="strategy-box">
                <div class="strat-name">{s.name}</div>
                <div class="strat-action"><strong>Action:</strong> {s.action}</div>
                <div class="strat-action" style="margin-top:4px;">
                  <strong>Why:</strong> {s.rationale}
                </div>
                <ul class="strat-tips">{tips_html}</ul>
              </div>"""

            cards += f"""
      <div class="ticker-card">
        <h3>{r.ticker} — {r.name} &nbsp; {badge}</h3>
        <div class="ticker-grid">
          <div class="ticker-item">
            <span class="lbl">Price: </span>
            <span class="val">${ind.price:,.2f}</span>
          </div>
          <div class="ticker-item">
            <span class="lbl">Trend: </span>
            <span class="val">{ind.trend}</span>
          </div>
          <div class="ticker-item">
            <span class="lbl">RSI: </span>
            <span class="val">{ind.rsi:.1f}
              {'⚠' if ind.rsi > 70 else ('↙' if ind.rsi < 30 else '✓')}
            </span>
          </div>
          <div class="ticker-item">
            <span class="lbl">ADX: </span>
            <span class="val">{ind.adx:.1f}
              {'(Strong)' if ind.adx > 25 else '(Weak)'}
            </span>
          </div>
          <div class="ticker-item">
            <span class="lbl">MACD: </span>
            <span class="val">{ind.macd_hist:+.4f}
              {'↑' if ind.macd_hist > 0 else '↓'}
            </span>
          </div>
          <div class="ticker-item">
            <span class="lbl">BB%: </span>
            <span class="val">{ind.bb_pct*100:.0f}%</span>
          </div>
          <div class="ticker-item">
            <span class="lbl">Fwd P/E: </span>
            <span class="val">{pe}</span>
          </div>
          <div class="ticker-item">
            <span class="lbl">PEG: </span>
            <span class="val">{peg}</span>
          </div>
          <div class="ticker-item">
            <span class="lbl">Market Cap: </span>
            <span class="val">{mc}</span>
          </div>
          <div class="ticker-item">
            <span class="lbl">Analyst Target: </span>
            <span class="val">{tgt}</span>
          </div>
          <div class="ticker-item">
            <span class="lbl">1M / 3M Return: </span>
            <span class="val">
              {self._ret_fmt(ind.ret_1m)} / {self._ret_fmt(ind.ret_3m)}
            </span>
          </div>
          <div class="ticker-item">
            <span class="lbl">Max Drawdown: </span>
            <span class="val">{ind.max_dd:.1f}%</span>
          </div>
        </div>
        <div style="margin-top:12px;font-size:12px;color:#64748b;">
          <strong>Score breakdown:</strong>
          {' | '.join(f'{k}: {v}' for k, v in ind.score_detail.items())}
        </div>
        {strat_html}
      </div>"""
        return cards

    def _backtest_section(self, report) -> str:
        if report is None:
            return ""

        rows = ""
        if report.summary_df is not None:
            for _, row in report.summary_df.iterrows():
                rows += f"""
          <tr>
            <td style="font-weight:700;">{row.get('Ticker','')}</td>
            <td>{row.get('Signals','')}</td>
            <td>{row.get('Score-Ret Corr','')}</td>
            <td>{row.get('Strong Hit%1M','')}</td>
            <td>{row.get('Strong Avg1M','')}</td>
            <td>{row.get('Strong Avg3M','')}</td>
            <td>{row.get('Sharpe(Strong)','')}</td>
          </tr>"""

        verdict_color = "#16a34a" if "Strong" in report.verdict else \
                        "#d97706" if "Moderate" in report.verdict else "#dc2626"

        return f"""
  <div class="section">
    <div class="section-title">Backtest Results</div>
    <div class="verdict-box" style="border-color:{verdict_color};
         background:{verdict_color}15;">
      <h3 style="color:{verdict_color};">
        Overall Score–Return Correlation: {report.overall_corr:+.3f}
      </h3>
      <p>{report.verdict}</p>
    </div>
    <table>
      <thead>
        <tr>
          <th>Ticker</th><th>Signals</th><th>Score-Ret Corr</th>
          <th>Strong Hit% 1M</th><th>Strong Avg 1M</th>
          <th>Strong Avg 3M</th><th>Sharpe (Strong)</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    <p style="font-size:11px;color:#94a3b8;margin-top:8px;">
      "Strong" bucket = tickers scoring 70–100. Hit% = % of signals
      with positive 1-month forward return.
    </p>
  </div>"""

    def _optimization_section(self, opt) -> str:
        if opt is None:
            return ""

        def weight_bars(weights: dict) -> str:
            bars = ""
            for k, v in sorted(weights.items(),
                                key=lambda x: x[1], reverse=True):
                pct = v * 100
                bars += f"""
              <div style="display:flex;align-items:center;margin-bottom:6px;">
                <div style="width:80px;font-size:11px;color:#64748b;">{k}</div>
                <div style="flex:1;background:#e2e8f0;border-radius:4px;height:8px;">
                  <div style="width:{pct:.0f}%;background:#3b82f6;
                       border-radius:4px;height:8px;"></div>
                </div>
                <div style="width:40px;text-align:right;font-size:11px;
                     font-weight:600;color:#1e293b;">{pct:.0f}%</div>
              </div>"""
            return bars

        ridge_cls = "model-box winner" if opt.winner.name == "Ridge Regression" \
                    else "model-box"
        rf_cls    = "model-box winner" if opt.winner.name == "Random Forest" \
                    else "model-box"

        return f"""
  <div class="section">
    <div class="section-title">Weight Optimization Results</div>
    <p style="font-size:13px;color:#475569;margin:0 0 16px;">
      Both Ridge Regression and Random Forest were trained on historical
      indicator data using walk-forward cross-validation.
      The winner was selected automatically based on out-of-sample R²,
      direction accuracy, and RMSE.
    </p>
    <p style="font-size:13px;font-weight:600;color:#1e293b;margin:0 0 12px;">
      🏆 Winner: {opt.winner.name}
    </p>
    <p style="font-size:12px;color:#64748b;margin:0 0 16px;">
      {opt.selection_reason}
    </p>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
      <div class="{ridge_cls}">
        <div style="font-weight:700;margin-bottom:8px;">
          Ridge Regression
          {'🏆 Selected' if opt.winner.name == 'Ridge Regression' else ''}
        </div>
        <div style="font-size:12px;color:#64748b;margin-bottom:10px;">
          R²: {opt.ridge.r2_oos:.4f} &nbsp;|&nbsp;
          Dir Acc: {opt.ridge.dir_accuracy:.1f}% &nbsp;|&nbsp;
          RMSE: {opt.ridge.rmse_oos:.4f}
        </div>
        {weight_bars(opt.ridge.weights)}
      </div>
      <div class="{rf_cls}">
        <div style="font-weight:700;margin-bottom:8px;">
          Random Forest
          {'🏆 Selected' if opt.winner.name == 'Random Forest' else ''}
        </div>
        <div style="font-size:12px;color:#64748b;margin-bottom:10px;">
          R²: {opt.random_forest.r2_oos:.4f} &nbsp;|&nbsp;
          Dir Acc: {opt.random_forest.dir_accuracy:.1f}% &nbsp;|&nbsp;
          RMSE: {opt.random_forest.rmse_oos:.4f}
        </div>
        {weight_bars(opt.random_forest.weights)}
      </div>
    </div>

    <div style="margin-top:16px;background:#f8fafc;border-radius:8px;
         padding:14px 16px;border:1px solid #e2e8f0;">
      <div style="font-size:13px;font-weight:600;margin-bottom:8px;">
        Optimal Weights Applied to Today's Scores
      </div>
      {weight_bars(opt.optimal_weights)}
    </div>
  </div>"""
