# Sigmo – Seed SQL Commands

## 1. Restaurant (Example ID: S0001)

```sql
INSERT INTO restaurants (restaurant_id, name, branch, manager_chat_id, opening_reminder_time, closing_reminder_time, reminder_followup_minutes)
VALUES (
  'S0001',
  'Sigmo Bistro',
  'Main Branch',             -- branch name, or NULL if not needed
  '<manager_telegram_chat_id>',
  '02:00',                   -- opening reminder time (24h, UTC). 02:00 UTC = 10:00 AM PHT.
  '14:00',                   -- closing reminder time (24h, UTC). 14:00 UTC = 10:00 PM PHT.
  20                         -- minutes after reminder to send follow-up if not started
);
```

## 2. Manager

```sql
INSERT INTO managers (chat_id, name, restaurant_id)
VALUES ('<manager_telegram_chat_id>', 'Manager Name', 'S0001');
```

## 3. Staff (repeat for each person)

```sql
INSERT INTO staff (chat_id, name, restaurant_id)
VALUES ('<staff_telegram_chat_id>', 'Staff Name', 'S0001');
```

## 4. Checklist Steps (All Types)

### Dining Opening
```sql
INSERT INTO checklist_steps (restaurant_id, checklist_id, step_number, instruction, requires_photo) VALUES
('S0001', 'DINING_OPEN', 1, 'Turn on lights', false),
('S0001', 'DINING_OPEN', 8, 'Set up tables and chairs inside and outside', true),
('S0001', 'DINING_OPEN', 25, 'Unlock doors', false);
```

### Dining Closing
```sql
INSERT INTO checklist_steps (restaurant_id, checklist_id, step_number, instruction, requires_photo) VALUES
('S0001', 'DINING_CLOSE', 1, 'Lock the doors', false),
('S0001', 'DINING_CLOSE', 7, 'Clean and sanitize tables and chairs', true),
('S0001', 'DINING_CLOSE', 26, 'Double-check doors are closed', true);
```

### Kitchen Opening
```sql
INSERT INTO checklist_steps (restaurant_id, checklist_id, step_number, instruction, requires_photo) VALUES
('S0001', 'KITCHEN_OPEN', 1, 'Turn on kitchen lights', false),
('S0001', 'KITCHEN_OPEN', 3, 'Check kitchen cleanliness', true),
('S0001', 'KITCHEN_OPEN', 18, 'Prepare service tools and utensils', false);
```

### Kitchen Closing
```sql
INSERT INTO checklist_steps (restaurant_id, checklist_id, step_number, instruction, requires_photo) VALUES
('S0001', 'KITCHEN_CLOSE', 1, 'Conduct evening inventory', true),
('S0001', 'KITCHEN_CLOSE', 4, 'Clean pizza prep station', true),
('S0001', 'KITCHEN_CLOSE', 18, 'Final kitchen cleanliness check', false);
```

---

## Notes
- **IDs MUST match bot code**: Use `_OPEN` and `_CLOSE` (NOT Opening/Closing).
- **Time is UTC**: Adjust your local time to UTC before inserting.
- **Photos**: Set `requires_photo` to `true` (t) or `false` (f).
