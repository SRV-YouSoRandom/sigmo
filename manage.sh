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

select_restaurant() {

  restaurants=$(
    $COMPOSE exec -T postgres psql -U sigmo -d sigmo -At \
    -c "SELECT restaurant_id || '|' || name FROM restaurants;"
  )

  if [[ -z "$restaurants" ]]; then
    echo "No restaurants found."
    pause
    return 1
  fi

  echo
  echo "Available Restaurants:"
  echo

  i=1
  while IFS="|" read -r id name; do
    echo "$i) $id | $name"
    ids[$i]=$id
    ((i++))
  done <<< "$restaurants"

  echo
  read -r -p "Select restaurant number: " choice

  if [[ -z "${ids[$choice]}" ]]; then
    echo "Invalid selection"
    pause
    return 1
  fi

  SELECTED_RESTAURANT="${ids[$choice]}"
}

add_staff() {

  select_restaurant || return
  restaurant="$SELECTED_RESTAURANT"

  chat_id=$(input_required "Staff chat_id: ")
  name=$(input_required "Staff name: ")

  echo
  echo "Add staff $name ($chat_id) to $restaurant?"

  if confirm; then
    run_sql "INSERT INTO staff (chat_id,name,restaurant_id)
    VALUES ('$chat_id','$name','$restaurant');"

    echo -e "${GREEN}Staff added${RESET}"
  fi

  pause
}

add_manager() {

  select_restaurant || return
  restaurant="$SELECTED_RESTAURANT"

  chat_id=$(input_required "Manager chat_id: ")
  name=$(input_required "Manager name: ")

  echo
  echo "Create manager $name?"

  if confirm; then
    run_sql "INSERT INTO managers (chat_id,name,restaurant_id)
    VALUES ('$chat_id','$name','$restaurant');"

    echo -e "${GREEN}Manager added${RESET}"
  fi

  pause
}

view_staff() {
  run_sql "SELECT chat_id,name,restaurant_id FROM staff;"
  pause
}

view_managers() {
  run_sql "SELECT chat_id,name,restaurant_id FROM managers;"
  pause
}

delete_staff() {

  chat_id=$(input_required "Chat ID to delete: ")

  echo
  echo -e "${YELLOW}Delete staff $chat_id?${RESET}"

  if confirm; then
    run_sql "DELETE FROM staff WHERE chat_id='$chat_id';"
    echo -e "${GREEN}Staff deleted${RESET}"
  fi

  pause
}

delete_restaurant() {

  select_restaurant || return
  restaurant="$SELECTED_RESTAURANT"

  echo
  echo -e "${RED}WARNING: deleting this removes all related data${RESET}"

  if confirm; then
    run_sql "DELETE FROM restaurants WHERE restaurant_id='$restaurant';"
    echo -e "${GREEN}Restaurant deleted${RESET}"
  fi

  pause
}

edit_reminders() {

  select_restaurant || return
  restaurant="$SELECTED_RESTAURANT"

  echo
  read -r -p "Opening reminder time (PH HH:MM or blank to keep): " open_time
  read -r -p "Closing reminder time (PH HH:MM or blank to keep): " close_time

  if [[ -n "$open_time" ]]; then
    open_utc=$(TZ=Asia/Manila date -d "$open_time" +"%H:%M" -u)

    run_sql "
    UPDATE restaurants
    SET opening_reminder_time='$open_utc'
    WHERE restaurant_id='$restaurant';
    "

    echo -e "${GREEN}Opening reminder stored as UTC $open_utc${RESET}"
  fi

  if [[ -n "$close_time" ]]; then
    close_utc=$(TZ=Asia/Manila date -d "$close_time" +"%H:%M" -u)

    run_sql "
    UPDATE restaurants
    SET closing_reminder_time='$close_utc'
    WHERE restaurant_id='$restaurant';
    "

    echo -e "${GREEN}Closing reminder stored as UTC $close_utc${RESET}"
  fi

  if [[ -z "$open_time" && -z "$close_time" ]]; then
    echo "No changes made."
  fi

  pause
}

add_checklist_step() {

  select_restaurant || return
  restaurant="$SELECTED_RESTAURANT"

  echo
  echo "Select Checklist"
  echo "1) Kitchen Opening"
  echo "2) Kitchen Closing"
  echo "3) Dining Opening"
  echo "4) Dining Closing"

  read -r -p "Select option: " c

  case "$c" in
    1) checklist="KITCHEN_OPEN" ;;
    2) checklist="KITCHEN_CLOSE" ;;
    3) checklist="DINING_OPEN" ;;
    4) checklist="DINING_CLOSE" ;;
    *) echo "Invalid"; pause; return ;;
  esac

  step=$(input_required "Step number: ")
  instruction=$(input_required "Instruction: ")

  read -r -p "Requires photo? (y/n): " photo

  if [[ "$photo" == "y" ]]; then
    photo=true
  else
    photo=false
  fi

  run_sql "
  INSERT INTO checklist_steps
  (restaurant_id,checklist_id,step_number,instruction,requires_photo)
  VALUES
  ('$restaurant','$checklist',$step,'$instruction',$photo);
  "

  echo -e "${GREEN}Checklist step added${RESET}"

  pause
}

menu() {

while true; do

clear

echo "================================"
echo "        SIGMO ADMIN TOOL        "
echo "================================"
echo
echo "1) Add Staff"
echo "2) Add Manager"
echo "3) View Staff"
echo "4) View Managers"
echo "5) Delete Staff"
echo "6) Delete Restaurant"
echo "7) Edit Reminder Times"
echo "8) Add Checklist Step"
echo "9) Exit"
echo

read -r -p "Select option: " choice

case "$choice" in
  1) add_staff ;;
  2) add_manager ;;
  3) view_staff ;;
  4) view_managers ;;
  5) delete_staff ;;
  6) delete_restaurant ;;
  7) edit_reminders ;;
  8) add_checklist_step ;;
  9) exit 0 ;;
  *) echo "Invalid option"; pause ;;
esac

done

}

menu