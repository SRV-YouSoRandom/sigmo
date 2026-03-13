# Sigmo – Seed SQL Commands

## 1. Restaurant

```sql
INSERT INTO restaurants (restaurant_id, name, branch, manager_chat_id, opening_reminder_time, closing_reminder_time, reminder_followup_minutes)
VALUES (
  'R001',
  'My Restaurant',
  'Makati',                  -- branch name, or NULL if not needed
  '<manager_telegram_chat_id>',
  '10:00',                   -- opening reminder time (24h, UTC). NULL to disable.
  '22:00',                   -- closing reminder time (24h, UTC). NULL to disable.
  20                         -- minutes after reminder to send follow-up if not started
);
```

## 2. Manager

```sql
INSERT INTO managers (chat_id, name, restaurant_id)
VALUES ('<manager_telegram_chat_id>', 'Manager Name', 'R001');
```

## 3. Staff (repeat for each person)

```sql
INSERT INTO staff (chat_id, name, restaurant_id)
VALUES ('<staff_telegram_chat_id>', 'Staff Name', 'R001');
```

## 4. Dining Opening checklist steps

```sql
INSERT INTO checklist_steps (restaurant_id, checklist_id, step_number, instruction, requires_photo) VALUES
('R001', 'DINING_OPEN', 1,  'Turn on lights', false),
('R001', 'DINING_OPEN', 2,  'Turn on AC', false),
('R001', 'DINING_OPEN', 3,  'Turn on sounds', false),
('R001', 'DINING_OPEN', 4,  'Turn on POS and let it boot', false),
('R001', 'DINING_OPEN', 5,  'Read endorsements if any', false),
('R001', 'DINING_OPEN', 6,  'Turn on coffee machine', false),
('R001', 'DINING_OPEN', 7,  'Turn on coffee grinder', false),
('R001', 'DINING_OPEN', 8,  'Set up tables and chairs inside and outside', false),
('R001', 'DINING_OPEN', 9,  'Sanitize tables and chairs inside and outside. Send a photo when done.', true),
('R001', 'DINING_OPEN', 10, 'Sweep floors inside', false),
('R001', 'DINING_OPEN', 11, 'Mop floors inside. Send a photo when done.', true),
('R001', 'DINING_OPEN', 12, 'Clean outdoor glasses. Send a photo when done.', true),
('R001', 'DINING_OPEN', 13, 'Sweep outside floor', false),
('R001', 'DINING_OPEN', 14, 'Mop outside floor. Send a photo when done.', true),
('R001', 'DINING_OPEN', 15, 'Clean toilet. Send a photo when done.', true),
('R001', 'DINING_OPEN', 16, 'Refill toilet tissues if needed', false),
('R001', 'DINING_OPEN', 17, 'Wash hands', false),
('R001', 'DINING_OPEN', 18, 'Set up plates and utensils per table. Send a photo when done.', true),
('R001', 'DINING_OPEN', 19, 'Calibrate coffee machine', false),
('R001', 'DINING_OPEN', 20, 'Check dining equipment if clean and functioning', false),
('R001', 'DINING_OPEN', 21, 'Conduct inventory', false),
('R001', 'DINING_OPEN', 22, 'Prepare POS and cash count. Send a photo when done.', true),
('R001', 'DINING_OPEN', 23, 'Clean condiments and unused plates and utensils', false),
('R001', 'DINING_OPEN', 24, 'Wait for opening time', false),
('R001', 'DINING_OPEN', 25, 'Unlock doors', false);
```

---

## Notes

- **Reminder times are in UTC.** Adjust for your timezone (e.g. if you're UTC+8, a 10:00 AM local reminder = `02:00` here).
- Set `opening_reminder_time` or `closing_reminder_time` to `NULL` to disable that reminder entirely.
- `reminder_followup_minutes` controls how long after the first reminder the follow-up fires if no checklist has been started.
- `branch` is optional — leave as `NULL` if you only have one location.
