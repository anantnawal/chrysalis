"""AgentEvolver Step-Level Credit Attribution Engine (Section 6.1 Mathematical Formulations)."""
import math
from typing import List, Dict, Any, Tuple
from app.config import (
    TARGET_P99_LATENCY_MS,
    HEALTH_WEIGHT_LATENCY,
    HEALTH_WEIGHT_5XX,
    HEALTH_WEIGHT_POOL,
    CREDIT_ALPHA,
    CREDIT_BETA,
)
from app.adk_agents.schemas import SystemMetrics, ActionExecutionSpan, StepCreditAttribution


class CreditAttributionEngine:
    """Computes fine-grained Shapley-inspired credit attribution over OpenTelemetry action execution spans."""

    def __init__(
        self,
        target_latency_ms: float = TARGET_P99_LATENCY_MS,
        w1: float = HEALTH_WEIGHT_LATENCY,
        w2: float = HEALTH_WEIGHT_5XX,
        w3: float = HEALTH_WEIGHT_POOL,
        alpha: float = CREDIT_ALPHA,
        beta: float = CREDIT_BETA,
    ):
        self.target_latency_ms = target_latency_ms
        self.w1 = w1
        self.w2 = w2
        self.w3 = w3
        self.alpha = alpha
        self.beta = beta

    def compute_health(self, s: SystemMetrics) -> float:
        """Compute system instability index H(S_t) = w1*(L/L_target) + w2*E + w3*U_pool."""
        normalized_latency = s.p99_latency_ms / self.target_latency_ms
        # Cap normalized latency for numerical stability
        clamped_latency = min(normalized_latency, 20.0)
        h = (
            self.w1 * clamped_latency
            + self.w2 * s.http_5xx_rate
            + self.w3 * s.db_pool_utilization
        )
        return h

    def evaluate_span(self, span: ActionExecutionSpan) -> StepCreditAttribution:
        """Calculate fine-grained credit attribution score C(a_t) for an action span."""
        h_pre = self.compute_health(span.pre_state_metrics)
        h_post = self.compute_health(span.post_state_metrics)

        # Delta health improvement: positive means system got healthier (instability reduced)
        delta_h = h_pre - h_post

        # Delta metrics
        delta_lat = span.pre_state_metrics.p99_latency_ms - span.post_state_metrics.p99_latency_ms
        delta_5xx = span.pre_state_metrics.http_5xx_rate - span.post_state_metrics.http_5xx_rate
        delta_pool = span.pre_state_metrics.db_pool_utilization - span.post_state_metrics.db_pool_utilization

        # Compute raw score C(a_t) = tanh(alpha * delta_h - beta * Cost)
        cost_term = self.beta * span.cost_usd
        raw_score = math.tanh(self.alpha * delta_h - cost_term)

        # Qualitative rationale formulation
        if raw_score >= 0.5:
            rationale = (
                f"Action '{span.tool_name}' drastically restored system stability: "
                f"P99 latency improved by {delta_lat:.1f}ms, 5xx rate dropped by {delta_5xx*100:.1f}%, "
                f"pool pressure relieved by {delta_pool*100:.1f}%."
            )
        elif raw_score > 0.0:
            rationale = (
                f"Action '{span.tool_name}' made modest positive progress (delta_H = +{delta_h:.2f})."
            )
        elif raw_score > -0.5:
            rationale = (
                f"Action '{span.tool_name}' introduced minor latency or compute cost with negligible benefit."
            )
        else:
            rationale = (
                f"Action '{span.tool_name}' exacerbated system instability: "
                f"P99 latency worsened by {-delta_lat:.1f}ms or 5xx rate rose by {-delta_5xx*100:.1f}%."
            )

        return StepCreditAttribution(
            span_id=span.span_id,
            tool_name=span.tool_name,
            action_type=span.input_parameters.get("action_type", "operational_patch"),
            delta_latency=round(delta_lat, 1),
            delta_5xx_rate=round(delta_5xx, 3),
            delta_pool_pressure=round(delta_pool, 3),
            attribution_score=round(raw_score, 2),
            rationale=rationale,
        )

    def evaluate_trajectory(self, spans: List[ActionExecutionSpan]) -> List[StepCreditAttribution]:
        """Compute attribution matrix across all trajectory action spans."""
        return [self.evaluate_span(span) for span in spans]

    def format_attribution_table(self, attributions: List[StepCreditAttribution]) -> str:
        """Render a formatted ASCII table of the attribution matrix."""
        headers = ["Span ID", "Tool / Action", "Delta Latency", "Delta 5xx", "Pool Delta", "Credit Score", "Verdict"]
        rows = []
        for a in attributions:
            verdict = "REWARDED (+)" if a.attribution_score > 0 else "PENALIZED (-)"
            rows.append([
                a.span_id[:13],
                a.tool_name[:32],
                f"{a.delta_latency:+7.1f} ms",
                f"{a.delta_5xx_rate*100:+5.1f}%",
                f"{a.delta_pool_pressure*100:+5.1f}%",
                f"{a.attribution_score:+5.2f}",
                verdict,
            ])

        col_widths = [max(len(row[i]) for row in [headers] + rows) for i in range(len(headers))]
        fmt = " | ".join(f"{{:<{w}}}" for w in col_widths)

        lines = [
            "=" * (sum(col_widths) + 3 * (len(col_widths) - 1)),
            "AGENTEVOLVER FINE-GRAINED STEP CREDIT ATTRIBUTION MATRIX",
            "=" * (sum(col_widths) + 3 * (len(col_widths) - 1)),
            fmt.format(*headers),
            "-" * (sum(col_widths) + 3 * (len(col_widths) - 1)),
        ]
        for r in rows:
            lines.append(fmt.format(*r))
        lines.append("=" * (sum(col_widths) + 3 * (len(col_widths) - 1)))
        return "\n".join(lines)
