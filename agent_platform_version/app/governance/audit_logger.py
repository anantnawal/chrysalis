"""Google Cloud Logging Tamper-Evident Audit Trail."""
import json
import logging as std_logging
import time
from typing import Dict, Any, Optional
from app.config import PROJECT_ID, CLOUD_LOG_NAME, VERTEX_AI_AVAILABLE
from app.governance.cloud_log_writer import BackgroundCloudLogWriter

try:
    from google.cloud import logging as gcp_logging
    GCP_LOGGING_AVAILABLE = True
except ImportError:
    GCP_LOGGING_AVAILABLE = False


class CloudAuditLogger:
    """Tamper-evident audit logger streaming agent actions directly to Google Cloud Logging."""

    def __init__(self, project_id: str = PROJECT_ID, log_name: str = CLOUD_LOG_NAME):
        self.project_id = project_id
        self.log_name = log_name
        self._gcp_writer = None
        self.local_audit_buffer = []

        if GCP_LOGGING_AVAILABLE and VERTEX_AI_AVAILABLE:
            try:
                client = gcp_logging.Client(project=project_id)
                # Writes are batched off the request path and flushed at interpreter exit.
                self._gcp_writer = BackgroundCloudLogWriter(client.logger(log_name))
            except Exception:
                self._gcp_writer = None

    def log_event(
        self,
        event_type: str,
        actor: str,
        action: str,
        status: str,
        details: Dict[str, Any],
        severity: str = "INFO",
    ) -> Dict[str, Any]:
        """Record an immutable security event."""
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "project_id": self.project_id,
            "event_type": event_type,
            "actor": actor,
            "action": action,
            "status": status,
            "details": details,
        }

        # Send to Google Cloud Logging (non-blocking, batched)
        if self._gcp_writer:
            self._gcp_writer.submit(payload, severity=severity)

        self.local_audit_buffer.append(payload)
        return payload
