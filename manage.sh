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

refresh_scheduler() {
  echo "Refreshing scheduler jobs..."
  result=$($COMPOSE exec -T fastapi sh -c "curl -s -X POST http://localhost:8000/internal/refresh-schedules" 2>&1)
  if echo "$result" | grep -q '"ok":true'; then
    echo -e "${GREEN}Scheduler refreshed.${RESET}"
  else
    echo -e "${YELLOW}Warning: Could not refresh scheduler (bot may need restart). Result: $result${RESET}"
  fi
}

# Returns data as: id|name|branch|...
query_sql() {
  $COMPOSE exec -T postgres psql -U sigmo -d sigmo -At -c "$1"
}

input_required() {
  local prompt="$1"
  local value

  while true; do
    read -r -p "$prompt (or 'q' to cancel): " value
    if [[ "$value" == "q" || "$value" == "back" ]]; then
      return 2
    fi
    if [[ -n "$value" ]]; then
      echo "$value"
      return 0
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
  read -r -p "Select restaurant number (or 'q' to cancel): " choice

  [[ "$choice" == "q" || "$choice" == "back" ]] && return 1

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
  local h m total_h
  IFS=':' read -r h m <<< "$pht_time"
  # PHT is UTC+8, so subtract 8 hours (wrap around midnight)
  total_h=$(( (10#$h - 8 + 24) % 24 ))
  printf "%02d:%02d" "$total_h" "$((10#$m))"
}

# ---------------------------------------------------------------------------
# Restaurant Operations
# ---------------------------------------------------------------------------

add_restaurant() {
  echo "--- Add Restaurant ---"
  id=$(input_required "Restaurant ID (e.g. R001)") || return
  name=$(input_required "Name") || return
  read -r -p "Branch (Optional, 'q' to cancel): " branch
  [[ "$branch" == "q" || "$branch" == "back" ]] && return
  
  manager_chat_id=$(input_required "Admin/Manager Telegram Chat ID") || return
  
  echo "Reminder Times (Format HH:MM in PHT, e.g. 10:00)"
  read -r -p "Opening Reminder [PHT] ('q' to cancel, blank to skip): " opht
  [[ "$opht" == "q" || "$opht" == "back" ]] && return
  read -r -p "Closing Reminder [PHT] ('q' to cancel, blank to skip): " cpht
  [[ "$cpht" == "q" || "$cpht" == "back" ]] && return
  read -r -p "Follow-up Delay (minutes, default 20, 'q' to cancel): " follow
  [[ "$follow" == "q" || "$follow" == "back" ]] && return

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
    refresh_scheduler
  fi
  pause
}

view_restaurants() {
  echo "--- All Restaurants ---"
  run_sql "SELECT restaurant_id, name, branch, manager_chat_id, opening_reminder_time as open_utc, closing_reminder_time as close_utc FROM restaurants ORDER BY name;"
  pause
}

update_restaurant() {
  select_restaurant || return
  id="$SELECTED_RESTAURANT"

  echo "Updating $id. Leave blank to keep current value, 'q' to cancel."
  read -r -p "New Name: " name
  [[ "$name" == "q" || "$name" == "back" ]] && return
  read -r -p "New Branch: " branch
  [[ "$branch" == "q" || "$branch" == "back" ]] && return
  read -r -p "New Manager Chat ID: " mid
  [[ "$mid" == "q" || "$mid" == "back" ]] && return
  read -r -p "Opening Reminder [PHT]: " opht
  [[ "$opht" == "q" || "$opht" == "back" ]] && return
  read -r -p "Closing Reminder [PHT]: " cpht
  [[ "$cpht" == "q" || "$cpht" == "back" ]] && return
  read -r -p "Follow-up Delay [mins]: " follow
  [[ "$follow" == "q" || "$follow" == "back" ]] && return

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

  refresh_scheduler
  echo -e "${GREEN}Update complete.${RESET}"
  pause
}

delete_restaurant() {
  select_restaurant || return
  id="$SELECTED_RESTAURANT"

  echo -e "${RED}WARNING: This will delete ALL data for $id (Staff, Managers, Steps, Sessions)${RESET}"
  if confirm; then
    # Delete in order of dependency
    echo "Cleaning up dependent records..."
    
    # 1. Step Photos (linked to sessions)
    run_sql "DELETE FROM step_photos WHERE session_id IN (SELECT id FROM sessions WHERE restaurant_id='$id');"
    
    # 2. Issue Reports
    run_sql "DELETE FROM issue_reports WHERE restaurant_id='$id';"
    
    # 3. Sessions
    run_sql "DELETE FROM sessions WHERE restaurant_id='$id';"
    
    # 4. Checklist Runs
    run_sql "DELETE FROM checklist_runs WHERE restaurant_id='$id';"
    
    # 5. Checklist Steps
    run_sql "DELETE FROM checklist_steps WHERE restaurant_id='$id';"
    
    # 6. Staff
    run_sql "DELETE FROM staff WHERE restaurant_id='$id';"
    
    # 7. Managers
    run_sql "DELETE FROM managers WHERE restaurant_id='$id';"
    
    # 8. Finally, the Restaurant
    run_sql "DELETE FROM restaurants WHERE restaurant_id='$id';"
    
    echo -e "${GREEN}Restaurant and all related data deleted.${RESET}"
    refresh_scheduler
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
  select_restaurant || return
  cid=$(input_required "Staff Chat ID") || return
  name=$(input_required "Staff Name") || return
  
  if confirm; then
    run_sql "INSERT INTO staff (chat_id, name, restaurant_id) VALUES ('$cid', '$name', '$SELECTED_RESTAURANT');"
    echo -e "${GREEN}Staff added.${RESET}"
  fi
  pause
}

view_staff() {
  echo "Filter by restaurant? (y/n, 'q' to cancel)"
  read -r filter
  [[ "$filter" == "q" || "$filter" == "back" ]] && return
  if [[ "$filter" == "y" ]]; then
    select_restaurant || return
    run_sql "SELECT chat_id, name FROM staff WHERE restaurant_id='$SELECTED_RESTAURANT';"
  else
    run_sql "SELECT chat_id, name, restaurant_id FROM staff ORDER BY restaurant_id;"
  fi
  pause
}

delete_staff() {
  cid=$(input_required "Chat ID to delete") || return
  echo -e "${YELLOW}Delete staff $cid and all related history?${RESET}"

  if confirm; then
    echo "Cleaning up dependent records..."
    # 1. Step Photos (linked to sessions)
    run_sql "DELETE FROM step_photos WHERE session_id IN (SELECT id FROM sessions WHERE chat_id='$cid');"
    # 2. Issue Reports
    run_sql "DELETE FROM issue_reports WHERE chat_id='$cid';"
    # 3. Sessions
    run_sql "DELETE FROM sessions WHERE chat_id='$cid';"
    # 4. Checklist Runs
    run_sql "DELETE FROM checklist_runs WHERE chat_id='$cid';"
    # 5. Finally, the Staff
    run_sql "DELETE FROM staff WHERE chat_id='$cid';"
    
    echo -e "${GREEN}Staff and related data deleted.${RESET}"
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
  select_restaurant || return
  cid=$(input_required "Manager Chat ID") || return
  name=$(input_required "Manager Name") || return
  
  if confirm; then
    run_sql "INSERT INTO managers (chat_id, name, restaurant_id) VALUES ('$cid', '$name', '$SELECTED_RESTAURANT');"
    echo -e "${GREEN}Manager added.${RESET}"
  fi
  pause
}

view_managers_op() {
  echo "Filter by restaurant? (y/n, 'q' to cancel)"
  read -r filter
  [[ "$filter" == "q" || "$filter" == "back" ]] && return
  if [[ "$filter" == "y" ]]; then
    select_restaurant || return
    run_sql "SELECT chat_id, name FROM managers WHERE restaurant_id='$SELECTED_RESTAURANT';"
  else
    run_sql "SELECT chat_id, name, restaurant_id FROM managers ORDER BY restaurant_id;"
  fi
  pause
}

delete_manager_op() {
  cid=$(input_required "Chat ID to delete") || return
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

_select_checklist_type() {
  echo "Select Checklist Type (or 'q' to cancel):"
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
    q|back) return 1 ;;
    *) echo "Invalid"; return 1 ;;
  esac
  export SELECTED_CHECKLIST_ID="$clid"
  return 0
}

add_checklist_step() {
  select_restaurant || return
  _select_checklist_type || return
  clid="$SELECTED_CHECKLIST_ID"

  num=$(input_required "Step Number") || return
  inst=$(input_required "Instruction") || return
  read -r -p "Requires Photo? (y/n, 'q' to cancel): " photo
  [[ "$photo" == "q" || "$photo" == "back" ]] && return
  [[ "$photo" == "y" ]] && photo="true" || photo="false"

  run_sql "INSERT INTO checklist_steps (restaurant_id, checklist_id, step_number, instruction, requires_photo)
  VALUES ('$SELECTED_RESTAURANT', '$clid', $num, '$inst', $photo);"
  echo -e "${GREEN}Step added.${RESET}"
  pause
}

view_checklist_steps() {
  select_restaurant || return
  run_sql "SELECT checklist_id, step_number, instruction, requires_photo FROM checklist_steps WHERE restaurant_id='$SELECTED_RESTAURANT' ORDER BY checklist_id, step_number;"
  pause
}

update_checklist_step() {
  select_restaurant || return
  _select_checklist_type || return
  clid="$SELECTED_CHECKLIST_ID"

  num=$(input_required "Step Number to update") || return
  
  # Verify step exists
  exists=$(query_sql "SELECT id FROM checklist_steps WHERE restaurant_id='$SELECTED_RESTAURANT' AND checklist_id='$clid' AND step_number=$num;")
  if [[ -z "$exists" ]]; then
    echo -e "${RED}Step not found.${RESET}"
    pause
    return
  fi

  echo "Updating Step $num. Leave blank to keep current value, 'q' to cancel."
  read -r -p "New Instruction: " inst
  [[ "$inst" == "q" || "$inst" == "back" ]] && return
  read -r -p "Change Requires Photo? (y/n/skip): " photo
  [[ "$photo" == "q" || "$photo" == "back" ]] && return

  [[ -n "$inst" ]] && run_sql "UPDATE checklist_steps SET instruction='$inst' WHERE restaurant_id='$SELECTED_RESTAURANT' AND checklist_id='$clid' AND step_number=$num;"
  
  if [[ "$photo" == "y" ]]; then
    run_sql "UPDATE checklist_steps SET requires_photo=true WHERE restaurant_id='$SELECTED_RESTAURANT' AND checklist_id='$clid' AND step_number=$num;"
  elif [[ "$photo" == "n" ]]; then
    run_sql "UPDATE checklist_steps SET requires_photo=false WHERE restaurant_id='$SELECTED_RESTAURANT' AND checklist_id='$clid' AND step_number=$num;"
  fi

  echo -e "${GREEN}Update complete.${RESET}"
  pause
}

delete_checklist_step() {
  select_restaurant || return
  _select_checklist_type || return
  clid="$SELECTED_CHECKLIST_ID"

  num=$(input_required "Step Number to delete") || return
  
  echo -e "${YELLOW}Delete step $num from $clid?${RESET}"
  if confirm; then
    run_sql "DELETE FROM checklist_steps WHERE restaurant_id='$SELECTED_RESTAURANT' AND checklist_id='$clid' AND step_number=$num;"
    echo -e "${GREEN}Step deleted.${RESET}"
  fi
  pause
}

checklist_menu() {
  while true; do
    clear
    echo "=== CHECKLIST OPERATIONS ==="
    echo "1. Add Step"
    echo "2. View Steps (by Restaurant)"
    echo "3. Update Step"
    echo "4. Delete Step"
    echo "5. Back"
    echo
    read -r -p "Select: " choice
    case "$choice" in
      1) add_checklist_step ;;
      2) view_checklist_steps ;;
      3) update_checklist_step ;;
      4) delete_checklist_step ;;
      5) return ;;
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