import json
import pandas as pd
from datetime import datetime, time, timedelta
from collections import defaultdict

# Constants for file names and configurable values
ASSUMPTIONS_FILE = "assumptions.json"
RATES_FILE = "rates.csv"
DAYS_OF_CHARGING = 1  # Number of days to simulate charging (e.g., two weekdays)
SUMMER_SEASON = 'Summer'
DAY_TYPE = 'Weekdays'
ALL = "All"
TOU_PRIORITY = {"Super Off-Peak": 0, "Off-Peak": 1, "Peak": 2}

# Sort function that uses the priority dictionary
def sort_by_tou_priority(entry):
    return TOU_PRIORITY.get(entry["tou_name"], 3)  # Default to 3 for any unlisted TOU name


def load_assumptions():
    """Load assumptions from JSON file."""
    with open(ASSUMPTIONS_FILE, "r") as file:
        return json.load(file)

def load_rate_data():
    """Load rate data from CSV and build the rate_plans dictionary."""
    data = pd.read_csv(RATES_FILE)
    rate_plans = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for _, row in data.iterrows():
        lse_name = row['LSE Name']
        plan_name = row['Plan Name']
        season = row['Season']
        day_type = row['Day Type']
        tou_name = row['TOU Name']
        start_time = datetime.strptime(row['Start Time'], "%I:%M %p").time()
        stop_time = datetime.strptime(row['Stop Time'], "%I:%M %p").time()
        rate = float(row['Rate'].replace('$', ''))

        # Store each entry with start and stop times
        rate_plans[f'{lse_name} {plan_name}'][season][day_type].append({
            "tou_name": tou_name,
            "start_time": start_time,
            "stop_time": stop_time,
            "rate": rate
        })
    return rate_plans

def _in_time_period(reverse_period, period_start, period_stop, entry_start, entry_stop):
    # 16:00 - 8:00 am, 12:am - 3pm, case 2 11PM - 3PM, 6AM - 12PM
    return reverse_period and (
        period_stop > entry_start or period_start < entry_stop or (
            period_start < entry_start and entry_start > entry_stop)
        # 9am - 11pm, 12am -3pm, 8am - 4pm
        ) or (period_start >= entry_start and period_stop < entry_stop) or period_stop >= entry_stop or (
            period_start < entry_start and period_start < entry_stop and entry_start > entry_stop)


def find_overlapping_entries(rate_plans, plan_name, season, day_type, period_start, period_stop):
    """
    Retrieve all entries that overlap with a given start and stop time period.
    Properly handles cases where either the period or the TOU entry crosses midnight.
    """
    overlapping_entries = []
    reverse_period = period_stop < period_start

    # Always include "All" as a day_type
    combined_rate_plans = rate_plans[plan_name][season][day_type] + rate_plans[plan_name][season][ALL]

    for entry in combined_rate_plans:
        entry_start = entry['start_time']
        entry_stop = entry['stop_time']
        # if entry['tou_name'] == "Super Off-Peak" and "Pacific Gas and Electric Company EV2" == plan_name:
        #     if "Pacific Gas and Electric Company EV2" == plan_name:
        #         print (">>>>", entry['tou_name'], entry, (period_start < entry_start and entry_start > entry_stop))
            # 16:00 - 8:00 am, 12:am - 3pm, case 2 11PM - 3PM
        if _in_time_period(reverse_period, period_start, period_stop, entry_start, entry_stop):
            overlapping_entries.append(entry)

    # if "Pacific Gas and Electric Company EV A" == plan_name:
    #     print("*" * 80)
    #     print(overlapping_entries)

    return overlapping_entries


def calculate_charging_cost_for_period(
        rate_plans,
        plan_name,
        season,
        day_type,
        period_start,
        period_stop,
        required_hours,
        level,
        charging_speed):
    """
    Calculate the cost for charging within a single period, prioritizing cheaper TOU periods:
    Super Off-Peak, then Off-Peak, and finally Peak if needed.
    """
    remaining_hours = required_hours
    charging_details = []

    # print(f"Starting calculation for {plan_name} with charging window {period_start} to {period_stop}")
    overlapping_entries = find_overlapping_entries(
        rate_plans, 
        plan_name, 
        season, 
        day_type, 
        period_start, 
        period_stop
    )
    overlapping_entries.sort(key=sort_by_tou_priority)

    for entry in overlapping_entries:
        if remaining_hours <= 0:
            break

        entry_start = entry['start_time']
        entry_stop = entry['stop_time']
        entry_rate = entry['rate']
        entry_tou_name = entry["tou_name"]

        entry_start_dt = datetime.combine(datetime.today(), entry_start)
        entry_stop_dt = datetime.combine(datetime.today(), entry_stop)
        print(entry_start_dt, entry_stop_dt, entry_start > entry_stop)
        #Count midnight as tomorrow for time differencing
        if entry_stop == time(0,0):
            entry_stop_dt += timedelta(days=1)
        period_start_dt = datetime.combine(datetime.today(), period_start)
        period_stop_dt = datetime.combine(datetime.today(), period_stop)

        # TODO Refactor, lots of copy paste code below
        reverse_period = period_stop < period_start
        # if reverse_period:
        #      period_stop_dt += timedelta(days=1)
        # 16:00 - 8:00 am, 12:am - 3pm, 12am - 6am
        if reverse_period:
            if period_stop > entry_start:
                time_difference = 0
                if (entry_start == time(0,0) and entry_stop < period_stop):
                    time_difference = entry_stop_dt - entry_start_dt
                else:
                    time_difference = period_stop_dt - entry_start_dt
                # print("1 period_start, period_stop, entry_start, entry_stop", period_start, period_stop, entry_start, entry_stop, time_difference)
                if time_difference > timedelta(0):
                    charging_time_in_period = min(time_difference.total_seconds() / 3600, remaining_hours)
                    remaining_hours -= charging_time_in_period
                    charging_details.append({
                        "period": f"{entry_start.strftime('%I:%M %p')} - {entry_stop.strftime('%I:%M %p')}",
                        "hours": charging_time_in_period,
                        "cost": charging_time_in_period * entry_rate * charging_speed,
                        "tou_name": entry_tou_name,
                        "level": level
                    })
            elif period_start < entry_stop:
                time_difference = 0
                if entry_stop > period_start:
                    time_difference = entry_stop_dt - max(period_start_dt, entry_start_dt)
                else:
                    time_difference = entry_start_dt - period_stop_dt
                # print("2 period_start, period_stop, entry_start, entry_stop", period_start, period_stop, entry_start, entry_stop, time_difference)
                if time_difference > timedelta(0):
                    charging_time_in_period = min(time_difference.total_seconds() / 3600, remaining_hours)
                    remaining_hours -= charging_time_in_period
                    charging_details.append({
                        "period": f"{entry_start.strftime('%I:%M %p')} - {entry_stop.strftime('%I:%M %p')}",
                        "hours": charging_time_in_period,
                        "cost": charging_time_in_period * entry_rate * charging_speed,
                        "tou_name": entry_tou_name,
                        "level": level
                    })
            # 16:00 - 8:00 am, 12:am - 3pm, case 2 11PM - 3PM
            elif period_start < entry_start and entry_start > entry_stop:
                end_time = min(period_stop_dt, entry_stop_dt)
                end_time += timedelta(days=1)
                time_difference = end_time - entry_start_dt
                # print("3 period_start, period_stop, entry_start, entry_stop", "time_difference", period_start, period_stop, entry_start, entry_stop, time_difference)
                if time_difference > timedelta(0):
                    charging_time_in_period = min(time_difference.total_seconds() / 3600, remaining_hours)
                    remaining_hours -= charging_time_in_period
                    charging_details.append({
                        "period": f"{entry_start.strftime('%I:%M %p')} - {entry_stop.strftime('%I:%M %p')}",
                        "hours": charging_time_in_period,
                        "cost": charging_time_in_period * entry_rate * charging_speed,
                        "tou_name": entry_tou_name,
                        "level": level
                    })
                
        # 9am - 11pm, 12am -3pm, 12am - 6pm
        else:
            if period_start >= entry_start and period_stop <= entry_stop:
                time_difference = period_start_dt - min(entry_stop_dt, period_stop_dt)
                if time_difference > timedelta(0):
                    charging_time_in_period = min(time_difference.total_seconds() / 3600, remaining_hours)
                    remaining_hours -= charging_time_in_period
                    charging_details.append({
                        "period": f"{entry_start.strftime('%I:%M %p')} - {entry_stop.strftime('%I:%M %p')}",
                        "hours": charging_time_in_period,
                        "cost": charging_time_in_period * entry_rate * charging_speed,
                        "tou_name": entry_tou_name,
                        "level": level
                    })
        # 9am - 11pm, 3pm -4pm
            elif period_stop >= entry_stop and entry_start < period_stop:
                time_difference = 0
                if entry_stop < entry_start:
                   time_difference = period_stop_dt - entry_start_dt
                else:
                    time_difference = min(entry_stop_dt, period_stop_dt) - max(period_start_dt, entry_start_dt)
                if time_difference > timedelta(0):
                    charging_time_in_period = min(time_difference.total_seconds() / 3600, remaining_hours)
                    remaining_hours -= charging_time_in_period
                    charging_details.append({
                        "period": f"{entry_start.strftime('%I:%M %p')} - {entry_stop.strftime('%I:%M %p')}",
                        "hours": charging_time_in_period,
                        "cost": charging_time_in_period * entry_rate * charging_speed,
                        "tou_name": entry_tou_name,
                        "level": level
                    })
            # 9am - 11pm, 12am -3pm, 11PM - 3PM
            elif period_start < entry_start and period_start < entry_stop and entry_start > entry_stop:
                time_difference = entry_start_dt - period_start_dt
                # print("period_start, period_stop, entry_start, entry_stop", period_start, period_stop, entry_start, entry_stop, time_difference)
                if time_difference > timedelta(0):
                    charging_time_in_period = min(time_difference.total_seconds() / 3600, remaining_hours)
                    remaining_hours -= charging_time_in_period
                    charging_details.append({
                        "period": f"{entry_start.strftime('%I:%M %p')} - {entry_stop.strftime('%I:%M %p')}",
                        "hours": charging_time_in_period,
                        "cost": charging_time_in_period * entry_rate * charging_speed,
                        "tou_name": entry_tou_name,
                        "level": level
                    })

    # if "Pacific Gas and Electric Company EV A" == plan_name:
    #     print("#" * 30)
    #     print(charging_details)

    return charging_details


def simulate_charging_costs(
    rate_plans, 
    driver_profiles,
    required_hours_per_day_level_2,
    required_hours_per_day_level_1,
    charger_kw_level_2,
    charger_kw_level_1
    ):
    """Simulate charging costs for each profile across all Plan Names over a two-day period."""
    charging_costs = defaultdict(lambda: defaultdict(list))

    for plan_name in rate_plans.keys():
        for profile_name, profile_data in driver_profiles.items():
            total_cost_for_two_days_level_2 = 0.0
            total_cost_for_two_days_level_1 = 0.0
            charging_details = []

            for _ in range(DAYS_OF_CHARGING):
                charging_start_time = datetime.strptime(profile_data["Charging Hours Start"], "%I:%M %p").time()
                charging_end_time = datetime.strptime(profile_data["Charging Hours End"], "%I:%M %p").time()

                daily_charging_details = calculate_charging_cost_for_period(
                    rate_plans, 
                    plan_name,
                    SUMMER_SEASON, DAY_TYPE,
                    charging_start_time,
                    charging_end_time,
                    required_hours_per_day_level_2,
                    "2",
                    charger_kw_level_2,
                )
       
                charging_details.extend(daily_charging_details)
                total_cost_for_two_days_level_2 += sum(entry['cost'] for entry in charging_details)

                if required_hours_per_day_level_1 <= 24:
                    daily_charging_details_l1 = calculate_charging_cost_for_period(
                        rate_plans, plan_name,
                        SUMMER_SEASON, DAY_TYPE,
                        charging_start_time,
                        charging_end_time,
                        required_hours_per_day_level_1,
                        "1",
                        charger_kw_level_1
                    )
                    charging_details.extend(daily_charging_details_l1)
                    total_cost_for_two_days_level_1 += sum(entry['cost'] for entry in charging_details) 

            charging_costs[profile_name][plan_name] = {
                "total_cost_level_2": total_cost_for_two_days_level_2,
                "total_cost_level_1": total_cost_for_two_days_level_1 - total_cost_for_two_days_level_2,
                "charging_details": charging_details
            }
    return charging_costs

def print_charging_costs(charging_costs, commute_name):
    """Print the total charging costs and detailed periods by TOU for each driver profile and plan name."""
    print(f"[{commute_name}] Charging Costs and Detailed Periods by TOU for Each Driver Profile and Plan Name:")
    output_rows = []
    
    for profile_name, plans in charging_costs.items():
        print(f"\n{profile_name}:")
        for plan_name, cost_data in plans.items():
            print(f"  Plan: {plan_name}")
            print(f"    Total Cost for One Day Level 1: ${cost_data['total_cost_level_1']:.2f}")
            print(f"    Total Cost for One Day Level 2: ${cost_data['total_cost_level_2']:.2f}")

            for detail in cost_data["charging_details"]:
                print(f"      Period: {detail['period']}, Hours: {detail['hours']:.2f}, Cost: ${detail['cost']:.2f}, TOU: {detail['tou_name']}")
                output_rows.append({
                    "Profile": profile_name,
                    "Plan": plan_name,
                    "Period": detail["period"],
                    "Hours": detail["hours"],
                    "Cost": detail["cost"],
                    "TOU": detail["tou_name"],
                    "Level": detail["level"]
                })

    # Output to CSV
    file_name = f"charging_costs_over_one_day_{commute_name}.csv"
    output_df = pd.DataFrame(output_rows)
    output_df.to_csv(file_name, index=False)
    print(f"\nResults have been saved to {file_name}")


def main():
    # Load assumptions and rate data
    assumptions = load_assumptions()
    rate_plans = load_rate_data()
    
    # Extract assumptions
    for name, distance in [
        ("average_commute", assumptions["average_commute_distance_miles"]),
        ("super_commute", assumptions["super_commute_distance_miles"])]:

        kwh_per_mile = assumptions["kwh_per_mile"]
        charger_kw_level_2 = assumptions["charger_kw_level_2"]
        charger_kw_level_1 = assumptions["charger_kw_level_1"]
        driver_profiles = assumptions["driver_profiles"]

        # Calculate the daily charging needs in kWh and hours
        daily_energy_kwh = distance * kwh_per_mile * 2  # round-trip
        required_hours_per_day_level_2 = daily_energy_kwh / charger_kw_level_2
        required_hours_per_day_level_1 = daily_energy_kwh / charger_kw_level_1

        # Simulate charging costs over two days
        # Todo don't pass in each level, pass in once and just call this one time
        # for each level
        charging_costs = simulate_charging_costs(
            rate_plans, 
            driver_profiles,
            required_hours_per_day_level_2,
            required_hours_per_day_level_1,
            charger_kw_level_2,
            charger_kw_level_1
        )

        # Print and save the results
        print_charging_costs(charging_costs, name)

# Run the main function
if __name__ == "__main__":
    main()
