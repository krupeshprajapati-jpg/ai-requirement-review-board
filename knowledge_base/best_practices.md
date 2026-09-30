# Clear and testable requirements

A strong requirement identifies the actor, the intended outcome, and the conditions under which the behavior is available. Name important inputs, validation rules, permissions, and observable success or failure behavior. Keep unspecified business decisions visible as questions instead of silently choosing values.

# Acceptance-criteria pattern

Use the format: **Given** a stated starting condition, **when** the user performs an action with a valid or invalid input, **then** the system produces a specific observable result. Include at least one normal path and relevant negative or boundary cases; avoid criteria that depend on words such as "quickly" or "appropriately" without measurable meaning.

# Operational details

For asynchronous or failure-prone actions, state what the user sees while work is pending, what happens after failure, and whether the action can safely be retried. For saved preferences or account changes, describe when the new value takes effect and how the user can confirm it was saved.