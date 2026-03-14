import json
import logging
from typing import Any, Dict, List

from models.schemas import CampaignStrategy, EmailContent, EmailVariant
from services.llm_service import LLMService

logger = logging.getLogger("campaignx.content_agent")


class ContentAgent:
    """
    Generates email subject + HTML body variants for each customer segment
    and A/B test variant defined in the strategy.
    """

    def __init__(self, llm_service: LLMService) -> None:
        self.llm = llm_service

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    # HTML template injected into the prompt so the LLM has a pixel-perfect
    # reference — it must fill in the CAPITALISED placeholders.
    _HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f9;font-family:Arial,Helvetica,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;padding:24px 0">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08)">

      <!-- HEADER -->
      <tr><td style="background:#1a3a5c;padding:24px 32px;text-align:center">
        <div style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:1px">SuperBFSI</div>
        <div style="font-size:11px;color:#a8c4e0;margin-top:4px;letter-spacing:2px;text-transform:uppercase">Trusted Banking Since 1985</div>
      </td></tr>

      <!-- HERO HEADLINE -->
      <tr><td style="padding:32px 32px 16px;text-align:center">
        <div style="font-size:26px;font-weight:800;color:#1a3a5c;line-height:1.3">HEADLINE_HERE</div>
        <div style="font-size:14px;color:#64748b;margin-top:8px">SUBHEADLINE_HERE</div>
      </td></tr>

      <!-- BENEFIT HIGHLIGHT BOX -->
      <tr><td style="padding:0 32px 24px">
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#e8f4fd;border-left:4px solid #1a3a5c;border-radius:6px">
          <tr><td style="padding:20px 24px">
            <div style="font-size:13px;color:#1a3a5c;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px">KEY BENEFIT</div>
            <div style="font-size:28px;font-weight:800;color:#1a3a5c">BENEFIT_NUMBER_HERE</div>
            <div style="font-size:13px;color:#334155;margin-top:4px">BENEFIT_DETAIL_HERE</div>
          </td></tr>
        </table>
      </td></tr>

      <!-- GREETING + BODY COPY -->
      <tr><td style="padding:0 32px 24px">
        <p style="font-size:15px;color:#1e293b;margin:0 0 16px">GREETING_HERE</p>
        <p style="font-size:14px;color:#334155;line-height:1.7;margin:0 0 16px">MAIN_COPY_HERE</p>
        <!-- BULLETS -->
        <table width="100%" cellpadding="0" cellspacing="0">
          BULLETS_HERE
        </table>
      </td></tr>

      <!-- URGENCY STRIP -->
      <tr><td style="padding:0 32px 28px">
        <div style="background:#fff8e1;border:1px solid #fbbf24;border-radius:6px;padding:12px 16px;font-size:13px;color:#92400e;font-weight:600">
          ⏰ URGENCY_LINE_HERE
        </div>
      </td></tr>

      <!-- CTA -->
      <tr><td style="padding:0 32px 32px;text-align:center">
        <a href="https://superbfsi.com/xdeposit/explore/"
           style="display:inline-block;background:#1a3a5c;color:#ffffff;font-size:16px;font-weight:700;
                  padding:16px 40px;border-radius:8px;text-decoration:none;letter-spacing:0.3px">
          CTA_TEXT_HERE &nbsp;→
        </a>
        <div style="font-size:12px;color:#94a3b8;margin-top:12px">No lock-in penalties. Cancel anytime.</div>
      </td></tr>

      <!-- DIVIDER -->
      <tr><td style="padding:0 32px"><hr style="border:none;border-top:1px solid #e2e8f0"></td></tr>

      <!-- FOOTER -->
      <tr><td style="padding:20px 32px;text-align:center">
        <div style="font-size:11px;color:#94a3b8;line-height:1.8">
          Interest rates are indicative and subject to change without prior notice.<br>
          T&amp;C apply. SuperBFSI is regulated by the Reserve Bank of India.<br>
          <a href="#" style="color:#94a3b8;text-decoration:underline">Unsubscribe</a> &nbsp;|&nbsp;
          <a href="#" style="color:#94a3b8;text-decoration:underline">Privacy Policy</a> &nbsp;|&nbsp;
          SuperBFSI, Mumbai — 400001
        </div>
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""

    def generate(self, brief: str, strategy: CampaignStrategy) -> EmailContent:
        logger.info(
            "ContentAgent: generating content  segments=%d  ab_variants=%d",
            len(strategy.customer_segments), len(strategy.ab_test_plan),
        )

        segments_info = [
            {
                "id":          s.id,
                "name":        s.name,
                "description": s.description,
                "criteria":    s.selection_criteria,
            }
            for s in strategy.customer_segments
        ]

        variants_to_write = [
            {
                "id":                 v.id,
                "name":               v.name,
                "hypothesis":         v.hypothesis,
                "target_segment_ids": v.target_segment_ids,
            }
            for v in strategy.ab_test_plan
        ]

        messages = [
            {
                "role": "system",
                "content": (
                    "You are the head of digital marketing at SuperBFSI, a leading Indian bank. "
                    "You write high-converting, beautifully designed HTML emails for Indian banking customers. "
                    "Your emails are:\n"
                    "  • Visually polished — structured HTML with inline CSS, mobile-first, max 600px wide\n"
                    "  • Segment-personalised — tone, offer framing and urgency differ by audience\n"
                    "  • Specific — you always use real numbers (rates, tenures, amounts) not vague promises\n"
                    "  • Compliant — no guaranteed return claims; all rates marked 'indicative p.a.'\n"
                    "  • Conversion-focused — one clear CTA, benefit box, urgency strip\n"
                    "You respond with a single valid JSON object. No markdown, no code fences, no prose."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Campaign brief:\n{brief}\n\n"
                    f"Campaign objective: {strategy.objective}\n\n"
                    f"Key messages: {json.dumps(strategy.key_messages)}\n\n"
                    f"Customer segments:\n{json.dumps(segments_info, indent=2)}\n\n"
                    f"Write one email for each of these A/B variants:\n{json.dumps(variants_to_write, indent=2)}\n\n"

                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "RETURN JSON with EXACTLY these keys:\n"
                    "  variants      — array (one item per variant above)\n"
                    "  explanation   — string\n"
                    "  reasoning_log — object\n\n"

                    "Each variant object must have:\n"
                    "  id          — MUST exactly match the variant id above\n"
                    "  segment_id  — MUST match one of the customer segment ids above\n"
                    "  name        — short display label\n"
                    "  subject     — plain text, MAX 60 chars, see rules below\n"
                    "  body_html   — full HTML email, see template and rules below\n"
                    "  rationale   — 2–3 sentences on copy strategy choices\n\n"

                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "SUBJECT LINE RULES:\n"
                    "  • MAX 60 characters — count carefully, hard limit\n"
                    "  • Must do ONE of: create urgency, trigger curiosity, show personal relevance\n"
                    "  • Include a specific number whenever possible\n"
                    "  • At most 1 emoji, placed at the end\n"
                    "  • GOOD: 'Earn 8.5% p.a. — rates dropping soon 🔒'\n"
                    "          'We miss you — your FD offer expires Friday'\n"
                    "          'Extra 0.25% FD rate — for women only 💰'\n"
                    "          'Your ₹1 lakh could earn ₹8,500 this year'\n"
                    "  • BAD:  'Special offer for you', 'Check this out!', anything vague\n\n"

                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "SEGMENT-SPECIFIC TONE AND CONTENT:\n\n"

                    "Senior citizens (age 60+):\n"
                    "  Tone: Warm, formal, reassuring. Start with 'Dear Valued Customer,'\n"
                    "  Focus: Safety of principal, fixed guaranteed tenure, RBI backing\n"
                    "  Numbers: e.g. '₹1,00,000 FD earns ₹8,500/year at 8.5% p.a.'\n"
                    "  Urgency: 'This rate is available for a limited period only'\n"
                    "  Avoid: FOMO language, trendy slang, complex financial jargon\n\n"

                    "Young professionals (age 25–35):\n"
                    "  Tone: Energetic, punchy, FOMO-driven. Start with 'Hey [Name],' or 'Hi there,'\n"
                    "  Focus: Beat inflation, grow faster than savings account, smart money move\n"
                    "  Numbers: e.g. 'Your savings account gives 3.5% — our FD gives 8.5%. Do the math.'\n"
                    "  Urgency: 'Rates being revised next month — lock in now'\n"
                    "  Style: Short punchy sentences. Max 2 lines per paragraph.\n\n"

                    "Women customers:\n"
                    "  Highlight: Extra 0.25% p.a. interest rate exclusively for women\n"
                    "  Tone: Empowering, acknowledging financial independence\n"
                    "  e.g. 'SuperBFSI rewards women investors with an additional 0.25% p.a.'\n\n"

                    "Inactive / lapsed customers:\n"
                    "  Hook: 'We miss you' re-engagement angle\n"
                    "  Tone: Warm, not pushy. 'It's been a while — here's what you've been missing'\n"
                    "  Offer: Come-back exclusive rate or waived minimum deposit\n\n"

                    "Tier 2/3 city customers:\n"
                    "  Focus: Accessible (100% online, no branch visit needed), trusted national bank\n"
                    "  Family angle: 'Secure your family's future from wherever you are'\n"
                    "  Simplicity: No jargon. Step-by-step language.\n\n"

                    "If a segment doesn't match a type above exactly, infer the best tone from their "
                    "name/description. NEVER generate generic placeholder content — always make it specific.\n\n"

                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "HTML TEMPLATE — fill in all CAPITALISED placeholders:\n\n"
                    f"{self._HTML_TEMPLATE}\n\n"

                    "Placeholder guide:\n"
                    "  HEADLINE_HERE       — big bold hook (max 10 words, segment-specific)\n"
                    "  SUBHEADLINE_HERE    — 1 supporting line (max 15 words)\n"
                    "  BENEFIT_NUMBER_HERE — the star metric, e.g. '8.5% p.a.' or '₹8,500/yr'\n"
                    "  BENEFIT_DETAIL_HERE — e.g. 'On deposits ≥ ₹50,000 for 2-year tenure'\n"
                    "  GREETING_HERE       — segment-appropriate greeting + 1-line personalisation\n"
                    "  MAIN_COPY_HERE      — 2–3 sentences, specific benefit, no fluff\n"
                    "  BULLETS_HERE        — 2–3 <tr> rows each containing a <td> bullet point:\n"
                    "                        use this pattern per bullet:\n"
                    "                        <tr><td style=\"padding:4px 0;font-size:14px;color:#334155\">"
                    "✓ &nbsp;BULLET TEXT</td></tr>\n"
                    "  URGENCY_LINE_HERE   — specific deadline or scarcity line (no vague 'limited time')\n"
                    "                        e.g. 'Offer valid till 31 March 2026. Rates revised quarterly.'\n"
                    "  CTA_TEXT_HERE       — action-oriented button label, e.g. 'Open My FD Now' or "
                    "'Claim My Rate'\n\n"

                    "The final body_html must be the COMPLETE filled-in HTML (no placeholders remaining). "
                    "Use only inline CSS. Do not add any <style> blocks."
                ),
            },
        ]

        raw = self.llm.chat_json(messages)
        content = self._parse(raw)
        logger.info("ContentAgent: done  variants=%d", len(content.variants))
        return content

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _parse(self, d: Dict[str, Any]) -> EmailContent:
        variants: List[EmailVariant] = []
        for item in d.get("variants", []):
            variants.append(
                EmailVariant(
                    id=item.get("id", ""),
                    segment_id=item.get("segment_id", ""),
                    name=item.get("name", ""),
                    subject=str(item.get("subject", ""))[:60],
                    body_html=str(item.get("body_html", ""))[:5000],
                    rationale=item.get("rationale", ""),
                )
            )
        return EmailContent(
            variants=variants,
            explanation=d.get("explanation", ""),
            reasoning_log=d.get("reasoning_log", {}),
        )
