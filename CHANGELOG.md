# 0.10.0

- Split plan compilation, rig state restoration, Action slot access and physics pre-roll into explicit modules, with compatibility imports retained.
- Fix dead fallback slot selection previously placed after the pre-roll function return. Bind a preferred/matching/single slot, and roll back ambiguous multi-slot assignments.
- Preserve the reverted 0.9.1 settle + transition buffer behavior, formal first-frame keys, placement, guard strength and FK/IK recovery.
- Add BA prop contact/release baking with isolated Actions and restoration, and read-only low-speed/velocity diagnostics.
- Keep one prompt per Clip; reject pasted control-document wrappers and show the 1000-character limit and exact scene FPS duration.
- Regression coverage: prop transform accuracy and restore, multi-slot rollback, fractional FPS metadata, rotated placement, adjustable arm guard, first-frame buffer, paired seam idempotence/mode switch/failure rollback and planted-foot reuse.
