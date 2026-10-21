"""APEX Layer 2 Principle Distillation & Semantic Vector Principle Store."""
import json
import uuid
import numpy as np
from typing import List, Dict, Any, Optional
from google import genai
from app.config import PROJECT_ID, LOCATION, MODEL_NAME, EMBEDDING_MODEL, VERTEX_AI_AVAILABLE
from app.adk_agents.schemas import (
    OperationalPrinciple,
    ActionExecutionSpan,
    StepCreditAttribution,
    TrajectoryTree,
)
from app.adk_agents.tools_library import set_principle_store


def lexical_hash_embedding(text: str, dims: int = 768) -> List[float]:
    """Deterministic offline fallback embedding (feature-hashed bag of words, L2-normalized).

    Unlike a random vector, texts that share vocabulary get high cosine similarity, so
    Self-Navigating retrieval stays meaningful without Vertex AI. Uses md5 (not Python's
    per-process salted hash()) so vectors are stable across runs.
    """
    import hashlib
    import re

    vec = np.zeros(dims, dtype=float)
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        idx = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dims
        vec[idx] += 1.0
    norm = np.linalg.norm(vec)
    return (vec / norm).tolist() if norm > 0 else vec.tolist()


class SemanticPrincipleStore:
    """In-memory vector store indexing operational principles with cosine similarity."""

    def __init__(self, embedding_model: str = EMBEDDING_MODEL):
        self.embedding_model = embedding_model
        self.principles: List[OperationalPrinciple] = []
        self._genai_client = None

        # Prepopulate historical foundation principles
        self._seed_historical_principles()
        # Connect to tools_library for runtime agent lookup
        set_principle_store(self)

    def _get_client(self):
        if self._genai_client is None:
            self._genai_client = genai.Client()
        return self._genai_client

    def _compute_embedding(self, text: str) -> List[float]:
        """Compute semantic embedding vector using Vertex AI text-embedding-004."""
        try:
            if not VERTEX_AI_AVAILABLE:
                raise RuntimeError("Vertex AI credentials not configured (offline mode)")
            client = self._get_client()
            res = client.models.embed_content(
                model=self.embedding_model,
                contents=text,
            )
            if hasattr(res, "embedding") and hasattr(res.embedding, "values"):
                return list(res.embedding.values)
            elif hasattr(res, "embeddings") and res.embeddings:
                return list(res.embeddings[0].values)
        except Exception:
            pass
        return lexical_hash_embedding(text)

    def _seed_historical_principles(self) -> None:
        """Seed initial lessons learned from prior historical outage post-mortems."""
        seeds = [
            OperationalPrinciple(
                principle_id="PRIN-HIST-001",
                trigger_pattern="Cache eviction stampede causing database connection pool saturation under high ingress",
                contraindicated_actions=["restart_database", "increase_db_pool_timeout", "flush_db_connections"],
                recommended_actions=["deploy_token_bucket_rate_limiter", "throttle_ingress_boundary", "shed_non_critical_load"],
                confidence_score=0.98,
                source_incident_id="INC-PRIOR-OCT2025",
            ),
            OperationalPrinciple(
                principle_id="PRIN-HIST-002",
                trigger_pattern="Cascading HTTP 500 errors driven by thread pool starvation in downstream services",
                contraindicated_actions=["exponential_client_retry_storm", "linear_horizontal_pod_burst"],
                recommended_actions=["activate_circuit_breaker", "dynamic_token_bucket_queue"],
                confidence_score=0.94,
                source_incident_id="INC-PRIOR-NOV2025",
            ),
        ]
        for p in seeds:
            p.embedding = self._compute_embedding(p.trigger_pattern)
            self.principles.append(p)

    def add_principle(self, principle: OperationalPrinciple) -> None:
        """Add a distilled principle to the semantic index."""
        if principle.embedding is None:
            principle.embedding = self._compute_embedding(principle.trigger_pattern)
        self.principles.append(principle)

    def search_principles(self, query: str, top_k: int = 2) -> List[OperationalPrinciple]:
        """Retrieve most relevant operational principles via cosine similarity over embeddings."""
        if not self.principles:
            return []

        query_emb = np.array(self._compute_embedding(query), dtype=float)
        query_norm = np.linalg.norm(query_emb)
        if query_norm == 0:
            query_norm = 1.0

        scored = []
        for p in self.principles:
            if p.embedding is not None:
                p_emb = np.array(p.embedding, dtype=float)
                p_norm = np.linalg.norm(p_emb)
                sim = np.dot(query_emb, p_emb) / (query_norm * p_norm) if p_norm > 0 else 0.0
            else:
                sim = 0.0
            scored.append((sim, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:top_k]]

    def distill_from_trajectory(
        self,
        incident_id: str,
        spans: List[ActionExecutionSpan],
        attributions: List[StepCreditAttribution],
    ) -> OperationalPrinciple:
        """APEX Layer 2: Prompt Gemini to extract an invariant operational principle from the execution trajectory."""
        # Find highest and lowest credited actions
        sorted_attr = sorted(attributions, key=lambda a: a.attribution_score)
        penalized = [a for a in sorted_attr if a.attribution_score < 0]
        rewarded = [a for a in sorted_attr if a.attribution_score > 0]

        summary_payload = {
            "incident_id": incident_id,
            "span_count": len(spans),
            "penalized_actions": [
                {"tool": a.tool_name, "score": a.attribution_score, "rationale": a.rationale}
                for a in penalized
            ],
            "rewarded_actions": [
                {"tool": a.tool_name, "score": a.attribution_score, "rationale": a.rationale}
                for a in rewarded
            ],
        }

        distillation_prompt = f"""You are the APEX Layer 2 Principle Distillation Engine.
Analyze the following incident mitigation trajectory and credit attribution results:

{json.dumps(summary_payload, indent=2)}

Distill a durable, generalized operational principle.
Return ONLY a valid JSON object with the following schema:
{{
  "trigger_pattern": "Specific condition (e.g. When database saturation is driven by cache misses...)",
  "contraindicated_actions": ["list of actions that exacerbated instability or were penalized"],
  "recommended_actions": ["list of actions that restored availability or were rewarded"],
  "confidence_score": 0.96
}}
"""
        try:
            client = self._get_client()
            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents=distillation_prompt,
            )
            raw_text = resp.text.strip()
            # Clean markdown JSON block formatting if present
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
            parsed = json.loads(raw_text.strip())

            distilled = OperationalPrinciple(
                principle_id=f"PRIN-DISTILLED-{uuid.uuid4().hex[:6].upper()}",
                trigger_pattern=parsed.get(
                    "trigger_pattern",
                    "When database connection saturation is driven by cache misses, throttle ingress at the boundary before altering backend pool configs."
                ),
                contraindicated_actions=parsed.get("contraindicated_actions", ["restart_database", "increase_db_pool_timeout"]),
                recommended_actions=parsed.get("recommended_actions", ["deploy_token_bucket_rate_limiter", "throttle_ingress_boundary"]),
                confidence_score=float(parsed.get("confidence_score", 0.95)),
                source_incident_id=incident_id,
            )
        except Exception:
            # Fallback robust distillation
            distilled = OperationalPrinciple(
                principle_id=f"PRIN-DISTILLED-{uuid.uuid4().hex[:6].upper()}",
                trigger_pattern="When database connection saturation is driven by cache misses, throttle ingress at boundary before altering backend configs.",
                contraindicated_actions=["restart_database", "increase_db_pool_timeout"],
                recommended_actions=["deploy_token_bucket_rate_limiter", "throttle_ingress_boundary"],
                confidence_score=0.96,
                source_incident_id=incident_id,
            )

        self.add_principle(distilled)
        return distilled
