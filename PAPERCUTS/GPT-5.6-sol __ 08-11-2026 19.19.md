---
description: Minor workflow friction observed during the TASK-012 independent verification session.
---

# Papercuts

- The first verifier-owned inline probe imported the private `Spa` ORM model
  from the package export instead of its owning module and stopped before
  creating database state. Importing it from
  `face_moment.serving_control.ingest_target` allowed the unchanged probe to
  proceed.
