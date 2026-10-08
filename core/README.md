# Core boundaries

`core/ports.py` contains small protocols for discovery, qualification,
enrichment, persistence, and external services. They are intentionally
behavior-free in this phase: existing implementations remain responsible for
their current behavior, while new application code can depend on stable
interfaces rather than provider-specific modules.
