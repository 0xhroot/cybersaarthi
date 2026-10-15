"""Local AI platform: llama.cpp runtime supervision, AI gateway, retrieval,
tools and provenance validation for the CyberSaarthi assistant.

The browser only ever talks to authenticated ``/api/v1/ai/*`` endpoints; the
inference server is bound to localhost and reached exclusively from the
backend. Authorization is enforced with the same dependencies and services
the rest of the API uses — never by the model.
"""

from app.ai.service import AIService

__all__ = ["AIService"]
