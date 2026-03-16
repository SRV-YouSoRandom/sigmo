#!/usr/bin/env bash

COMPOSE="docker compose -f docker-compose.prod.yml"

run_sql () {
    $COMPOSE exec -T postgres psql -U sigmo -d sigmo -c "$1"
}

color_green="\033[32m"
color_red="\033[31m"
color_yellow="\033[33m"
color_reset="\033[0m"

pause () {
    read -r -p "Press ENTER to continue..."
}

confirm () {
    read -r -p "Confirm (y/n): " ans
    [[ "$ans" == "y" || "$ans" == "Y" ]]
}

input_required () {
    local prompt="$1"
    local value

    while true; do
        read -r -p "$prompt" value
        if [[ -n "$value" ]]; then
            echo "$value"
            return
        else
            echo -e "${color_red}Value cannot be empty${color_reset}"
        fi
    done
}

add_staff () {

    chat_id=$(input_required "Staff chat_id: ")
    name=$(input_required "Staff name: ")
    restaurant=$(input_required "Restaurant ID: ")

    echo
    echo "Add staff $name ($chat_id) to $restaurant?"

    if confirm; then
        run_sql "INSERT INTO staff (chat_id,name,restaurant_id) VALUES ('$chat_id','$name','$restaurant');"
        echo -e "${color_green}Staff added${color_reset}"
    fi

    pause
}

add_manager () {

    chat_id=$(input_required "Manager chat_id: ")
    name=$(input_required "Manager name: ")
    restaurant=$(input_required "Restaurant ID: ")

    echo
    echo "Create manager $name?"

    if confirm; then
        run_sql "INSERT INTO managers (chat_id,name,restaurant_id) VALUES ('$chat_id','$name','$restaurant');"
        echo -e "${color_green}Manager added${color_reset}"
    fi

    pause
}

view_staff () {
    run_sql "SELECT chat_id,name,restaurant_id FROM staff;"
    pause
}

view_managers () {
    run_sql "SELECT chat_id,name,restaurant_id FROM managers;"
    pause
}

delete_staff () {

    chat_id=$(input_required "Chat ID to delete: ")

    echo
    echo -e "${color_yellow}Delete staff $chat_id?${color_reset}"

    if confirm; then
        run_sql "DELETE FROM staff WHERE chat_id='$chat_id';"
        echo -e "${color_green}Staff deleted${color_reset}"
    fi

    pause
}

delete_restaurant () {

    rid=$(input_required "Restaurant ID: ")

    echo
    echo -e "${color_red}WARNING: deleting restaurant removes all related data${color_reset}"

    if confirm; then
        run_sql "DELETE FROM restaurants WHERE restaurant_id='$rid';"
        echo -e "${color_green}Restaurant deleted${color_reset}"
    fi

    pause
}

edit_reminders () {

    rid=$(input_required "Restaurant ID: ")

    read -r -p "Opening reminder time (HH:MM or blank): " open_time
    read -r -p "Closing reminder time (HH:MM or blank): " close_time

    run_sql "
    UPDATE restaurants
    SET opening_reminder_time='${open_time:-NULL}',
        closing_reminder_time='${close_time:-NULL}'
    WHERE restaurant_id='$rid';
    "

    echo -e "${color_green}Reminder times updated${color_reset}"

    pause
}

add_checklist_step () {

    rid=$(input_required "Restaurant ID: ")
    checklist=$(input_required "Checklist ID (e.g DINING_OPEN): ")
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
    ('$rid','$checklist',$step,'$instruction',$photo);
    "

    echo -e "${color_green}Checklist step added${color_reset}"

    pause
}

menu () {

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

*)
echo "Invalid option"
pause
;;

esac

done

}

menu