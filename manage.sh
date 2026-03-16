#!/usr/bin/env bash

export TZ=Asia/Manila

COMPOSE="docker compose -f docker-compose.prod.yml"

color_green="\033[32m"
color_red="\033[31m"
color_yellow="\033[33m"
color_reset="\033[0m"

run_sql () {
    $COMPOSE exec -T postgres psql -U sigmo -d sigmo -c "$1"
}

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

select_restaurant () {

    echo
    echo "Available Restaurants:"
    $COMPOSE exec -T postgres psql -U sigmo -d sigmo -At -c \
    "SELECT restaurant_id || ' | ' || name FROM restaurants;" \
    | nl

    echo
    read -r -p "Select restaurant number: " choice

    restaurant=$(
        $COMPOSE exec -T postgres psql -U sigmo -d sigmo -At -c \
        "SELECT restaurant_id FROM restaurants;" | sed -n "${choice}p"
    )

    if [[ -z "$restaurant" ]]; then
        echo "Invalid selection"
        pause
        return 1
    fi

    echo "$restaurant"
}

select_checklist () {

    echo
    echo "Select Checklist:"
    echo "1) Kitchen Opening"
    echo "2) Kitchen Closing"
    echo "3) Dining Opening"
    echo "4) Dining Closing"

    read -r -p "Select option: " choice

    case "$choice" in
        1) echo "KITCHEN_OPEN" ;;
        2) echo "KITCHEN_CLOSE" ;;
        3) echo "DINING_OPEN" ;;
        4) echo "DINING_CLOSE" ;;
        *) echo "" ;;
    esac
}

add_staff () {

    restaurant=$(select_restaurant) || return

    chat_id=$(input_required "Staff chat_id: ")
    name=$(input_required "Staff name: ")

    echo
    echo "Add staff $name ($chat_id) to $restaurant?"

    if confirm; then
        run_sql "INSERT INTO staff (chat_id,name,restaurant_id)
        VALUES ('$chat_id','$name','$restaurant');"
        echo -e "${color_green}Staff added${color_reset}"
    fi

    pause
}

add_manager () {

    restaurant=$(select_restaurant) || return

    chat_id=$(input_required "Manager chat_id: ")
    name=$(input_required "Manager name: ")

    echo
    echo "Create manager $name?"

    if confirm; then
        run_sql "INSERT INTO managers (chat_id,name,restaurant_id)
        VALUES ('$chat_id','$name','$restaurant');"
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

    restaurant=$(select_restaurant) || return

    echo
    echo -e "${color_red}WARNING: this deletes the restaurant and related data${color_reset}"

    if confirm; then
        run_sql "DELETE FROM restaurants WHERE restaurant_id='$restaurant';"
        echo -e "${color_green}Restaurant deleted${color_reset}"
    fi

    pause
}

edit_reminders () {

    restaurant=$(select_restaurant) || return

    read -r -p "Opening reminder time (PH HH:MM or blank to keep): " open_time
    read -r -p "Closing reminder time (PH HH:MM or blank to keep): " close_time

    if [[ -n "$open_time" ]]; then
        open_utc=$(date -d "$open_time" -u +"%H:%M")
        run_sql "UPDATE restaurants
        SET opening_reminder_time='$open_utc'
        WHERE restaurant_id='$restaurant';"

        echo -e "${color_green}Opening reminder stored as UTC $open_utc${color_reset}"
    fi

    if [[ -n "$close_time" ]]; then
        close_utc=$(date -d "$close_time" -u +"%H:%M")
        run_sql "UPDATE restaurants
        SET closing_reminder_time='$close_utc'
        WHERE restaurant_id='$restaurant';"

        echo -e "${color_green}Closing reminder stored as UTC $close_utc${color_reset}"
    fi

    if [[ -z "$open_time" && -z "$close_time" ]]; then
        echo "No changes made."
    fi

    pause
}

add_checklist_step () {

    restaurant=$(select_restaurant) || return

    checklist=$(select_checklist)

    if [[ -z "$checklist" ]]; then
        echo "Invalid checklist selection"
        pause
        return
    fi

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