#!/usr/bin/env bash

COMPOSE="docker compose -f docker-compose.prod.yml"

GREEN="\033[32m"
RED="\033[31m"
YELLOW="\033[33m"
RESET="\033[0m"

pause() {
  read -r -p "Press ENTER to continue..."
}

confirm() {
  read -r -p "Confirm (y/n): " ans
  [[ "$ans" == "y" || "$ans" == "Y" ]]
}

run_sql() {
  $COMPOSE exec -T postgres psql -U sigmo -d sigmo -c "$1"
}

# Returns data as: id|name|branch|...
query_sql() {
  $COMPOSE exec -T postgres psql -U sigmo -d sigmo -At -c "$1"
}

input_required() {
  local prompt="$1"
  local value

  while true; do
    read -r -p "$prompt" value
    if [[ -n "$value" ]]; then
      echo "$value"
      return
    else
      echo -e "${RED}Value cannot be empty${RESET}"
    fi
  done
}

# ---------------------------------------------------------------------------
# Restaurant Selection Helper
# ---------------------------------------------------------------------------

select_restaurant() {
  restaurants=$(query_sql "SELECT restaurant_id || '|' || name || ' (' || COALESCE(branch, 'No Branch') || ')' FROM restaurants ORDER BY name ASC;")

  if [[ -z "$restaurants" ]]; then
    echo -e "${YELLOW}No restaurants found.${RESET}"
    return 1
  fi

  echo
  echo "Available Restaurants:"
  local i=1
  declare -g -A ids
  while IFS="|" read -r id display; do
    echo "$i) $id | $display"
    ids[$i]=$id
    ((i++))
  done <<< "$restaurants"

  echo
  read -r -p "Select restaurant number: " choice

  if [[ -z "${ids[$choice]}" ]]; then
    echo -e "${RED}Invalid selection${RESET}"
    return 1
  fi

  SELECTED_RESTAURANT="${ids[$choice]}"
}

# ---------------------------------------------------------------------------
# Time Conversion Helper (PHT to UTC)
# ---------------------------------------------------------------------------

convert_pht_to_utc() {
  local pht_time="$1"
  # PHP/PHT is UTC+8. We use TZ=Asia/Manila to ensure standard conversion.
  # Note: 'date' behavior varies; this is for standard Linux date (GNU).
  TZ=Asia/Manila date -d "$pht_time" +"%H:%M" -u 2>/dev/null
}

# ---------------------------------------------------------------------------
# Restaurant Operations
# ---------------------------------------------------------------------------

add_restaurant() {
  echo "--- Add Restaurant ---"
  id=$(input_required "Restaurant ID (e.g. R001): ")
  name=$(input_required "Name: ")
  read -r -p "Branch (Optional): " branch
  manager_chat_id=$(input_required "Admin/Manager Telegram Chat ID: ")
  
  echo "Reminder Times (Format HH:MM in PHT, e.g. 10:00)"
  read -r -p "Opening Reminder [PHT]: " opht
  read -r -p "Closing Reminder [PHT]: " cpht
  read -r -p "Follow-up Delay (minutes, default 20): " follow

  [[ -z "$follow" ]] && follow=20

  outc="NULL"
  cutc="NULL"
  [[ -n "$opht" ]] && outc="'$(convert_pht_to_utc "$opht")'"
  [[ -n "$cpht" ]] && cutc="'$(convert_pht_to_utc "$cpht")'"

  echo
  echo "Create restaurant $name?"
  if confirm; then
    run_sql "INSERT INTO restaurants (restaurant_id, name, branch, manager_chat_id, opening_reminder_time, closing_reminder_time, reminder_followup_minutes)
    VALUES ('$id', '$name', '${branch:-NULL}', '$manager_chat_id', $outc, $cutc, $follow);"
    echo -e "${GREEN}Restaurant created.${RESET}"
  fi
  pause
}

view_restaurants() {
  echo "--- All Restaurants ---"
  run_sql "SELECT restaurant_id, name, branch, manager_chat_id, opening_reminder_time as open_utc, closing_reminder_time as close_utc FROM restaurants ORDER BY name;"
  pause
}

update_restaurant() {
  select_restaurant || { pause; return; }
  id="$SELECTED_RESTAURANT"

  echo "Updating $id. Leave blank to keep current value."
  read -r -p "New Name: " name
  read -r -p "New Branch: " branch
  read -r -p "New Manager Chat ID: " mid
  read -r -p "Opening Reminder [PHT]: " opht
  read -r -p "Closing Reminder [PHT]: " cpht
  read -r -p "Follow-up Delay [mins]: " follow

  [[ -n "$name" ]] && run_sql "UPDATE restaurants SET name='$name' WHERE restaurant_id='$id';"
  [[ -n "$branch" ]] && run_sql "UPDATE restaurants SET branch='$branch' WHERE restaurant_id='$id';"
  [[ -n "$mid" ]] && run_sql "UPDATE restaurants SET manager_chat_id='$mid' WHERE restaurant_id='$id';"
  [[ -n "$follow" ]] && run_sql "UPDATE restaurants SET reminder_followup_minutes=$follow WHERE restaurant_id='$id';"
  
  if [[ -n "$opht" ]]; then
    outc=$(convert_pht_to_utc "$opht")
    run_sql "UPDATE restaurants SET opening_reminder_time='$outc' WHERE restaurant_id='$id';"
  fi
  if [[ -n "$cpht" ]]; then
    cutc=$(convert_pht_to_utc "$cpht")
    run_sql "UPDATE restaurants SET closing_reminder_time='$cutc' WHERE restaurant_id='$id';"
  fi

  echo -e "${GREEN}Update complete.${RESET}"
  pause
}

delete_restaurant() {
  select_restaurant || { pause; return; }
  echo -e "${RED}WARNING: This will delete ALL data for $SELECTED_RESTAURANT (Staff, Managers, Steps)${RESET}"
  if confirm; then
    run_sql "DELETE FROM restaurants WHERE restaurant_id='$SELECTED_RESTAURANT';"
    echo -e "${GREEN}Deleted.${RESET}"
  fi
  pause
}

restaurant_menu() {
  while true; do
    clear
    echo "=== RESTAURANT OPERATIONS ==="
    echo "1. Add Restaurant"
    echo "2. View All Restaurants"
    echo "3. Update Restaurant"
    echo "4. Delete Restaurant"
    echo "5. Back"
    echo
    read -r -p "Select: " choice
    case "$choice" in
      1) add_restaurant ;;
      2) view_restaurants ;;
      3) update_restaurant ;;
      4) delete_restaurant ;;
      5) return ;;
      *) echo "Invalid option"; sleep 1 ;;
    esac
  done
}

# ---------------------------------------------------------------------------
# Staff Operations
# ---------------------------------------------------------------------------

add_staff() {
  select_restaurant || { pause; return; }
  cid=$(input_required "Staff Chat ID: ")
  name=$(input_required "Staff Name: ")
  
  if confirm; then
    run_sql "INSERT INTO staff (chat_id, name, restaurant_id) VALUES ('$cid', '$name', '$SELECTED_RESTAURANT');"
    echo -e "${GREEN}Staff added.${RESET}"
  fi
  pause
}

view_staff() {
  echo "Filter by restaurant? (y/n)"
  read -r filter
  if [[ "$filter" == "y" ]]; then
    select_restaurant || { pause; return; }
    run_sql "SELECT chat_id, name FROM staff WHERE restaurant_id='$SELECTED_RESTAURANT';"
  else
    run_sql "SELECT chat_id, name, restaurant_id FROM staff ORDER BY restaurant_id;"
  fi
  pause
}

delete_staff() {
  cid=$(input_required "Chat ID to delete: ")
  if confirm; then
    run_sql "DELETE FROM staff WHERE chat_id='$cid';"
    echo -e "${GREEN}Deleted.${RESET}"
  fi
  pause
}

staff_menu() {
  while true; do
    clear
    echo "=== STAFF OPERATIONS ==="
    echo "1. Add Staff"
    echo "2. View Staff"
    echo "3. Delete Staff"
    echo "4. Back"
    echo
    read -r -p "Select: " choice
    case "$choice" in
      1) add_staff ;;
      2) view_staff ;;
      3) delete_staff ;;
      4) return ;;
      *) echo "Invalid option"; sleep 1 ;;
    esac
  done
}

# ---------------------------------------------------------------------------
# Manager Operations
# ---------------------------------------------------------------------------

add_manager_op() {
  select_restaurant || { pause; return; }
  cid=$(input_required "Manager Chat ID: ")
  name=$(input_required "Manager Name: ")
  
  if confirm; then
    run_sql "INSERT INTO managers (chat_id, name, restaurant_id) VALUES ('$cid', '$name', '$SELECTED_RESTAURANT');"
    echo -e "${GREEN}Manager added.${RESET}"
  fi
  pause
}

view_managers_op() {
  echo "Filter by restaurant? (y/n)"
  read -r filter
  if [[ "$filter" == "y" ]]; then
    select_restaurant || { pause; return; }
    run_sql "SELECT chat_id, name FROM managers WHERE restaurant_id='$SELECTED_RESTAURANT';"
  else
    run_sql "SELECT chat_id, name, restaurant_id FROM managers ORDER BY restaurant_id;"
  fi
  pause
}

delete_manager_op() {
  cid=$(input_required "Chat ID to delete: ")
  if confirm; then
    run_sql "DELETE FROM managers WHERE chat_id='$cid';"
    echo -e "${GREEN}Deleted.${RESET}"
  fi
  pause
}

manager_menu() {
  while true; do
    clear
    echo "=== MANAGER OPERATIONS ==="
    echo "1. Add Manager"
    echo "2. View Managers"
    echo "3. Delete Manager"
    echo "4. Back"
    echo
    read -r -p "Select: " choice
    case "$choice" in
      1) add_manager_op ;;
      2) view_managers_op ;;
      3) delete_manager_op ;;
      4) return ;;
      *) echo "Invalid option"; sleep 1 ;;
    esac
  done
}

# ---------------------------------------------------------------------------
# Checklist Operations
# ---------------------------------------------------------------------------

add_checklist_step() {
  select_restaurant || { pause; return; }
  echo "Select Checklist Type:"
  echo "1. Kitchen Opening"
  echo "2. Kitchen Closing"
  echo "3. Dining Opening"
  echo "4. Dining Closing"
  read -r -p "Choice: " c
  case "$c" in
    1) clid="KITCHEN_OPEN" ;;
    2) clid="KITCHEN_CLOSE" ;;
    3) clid="DINING_OPEN" ;;
    4) clid="DINING_CLOSE" ;;
    *) echo "Invalid"; pause; return ;;
  esac

  num=$(input_required "Step Number: ")
  inst=$(input_required "Instruction: ")
  read -r -p "Requires Photo? (y/n): " photo
  [[ "$photo" == "y" ]] && photo="true" || photo="false"

  run_sql "INSERT INTO checklist_steps (restaurant_id, checklist_id, step_number, instruction, requires_photo)
  VALUES ('$SELECTED_RESTAURANT', '$clid', $num, '$inst', $photo);"
  echo -e "${GREEN}Step added.${RESET}"
  pause
}

view_checklist_steps() {
  select_restaurant || { pause; return; }
  run_sql "SELECT checklist_id, step_number, instruction, requires_photo FROM checklist_steps WHERE restaurant_id='$SELECTED_RESTAURANT' ORDER BY checklist_id, step_number;"
  pause
}

checklist_menu() {
  while true; do
    clear
    echo "=== CHECKLIST OPERATIONS ==="
    echo "1. Add Step"
    echo "2. View Steps (by Restaurant)"
    echo "3. Back"
    echo
    read -r -p "Select: " choice
    case "$choice" in
      1) add_checklist_step ;;
      2) view_checklist_steps ;;
      3) return ;;
      *) echo "Invalid option"; sleep 1 ;;
    esac
  done
}

# ---------------------------------------------------------------------------
# Main Execution Loop
# ---------------------------------------------------------------------------

main_menu() {
  while true; do
    clear
    echo "================================"
    echo "        SIGMO ADMIN TOOL        "
    echo "================================"
    echo
    echo "1) Staff Operations"
    echo "2) Manager Operations"
    echo "3) Restaurant Operations"
    echo "4) Checklist Operations"
    echo "5) Exit"
    echo
    read -r -p "Select option: " choice
    case "$choice" in
      1) staff_menu ;;
      2) manager_menu ;;
      3) restaurant_menu ;;
      4) checklist_menu ;;
      5) exit 0 ;;
      *) echo -e "${RED}Invalid selection${RESET}"; sleep 1 ;;
    esac
  done
}

main_menu