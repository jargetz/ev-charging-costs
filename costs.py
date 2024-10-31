import json
import pandas as pd
from datetime import datetime, time, timedelta
from collections import defaultdict

# Constants for file names and configurable values
ASSUMPTIONS_FILE = "assumptions.json"
RATES_FILE = "rates.csv"
OUTPUT_CSV_FILE = "charging_costs_over_two_days.csv"
DAYS_OF_CHARGING = 2  # Number of days to simulate charging (e.g., two weekdays)
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
        # 16:00 - 8:00 am, 12:am - 3pm
        if reverse_period:
            if period_stop > entry_start or period_start < entry_stop:
                overlapping_entries.append(entry)
        # 9am - 11pm, 12am -3pm
        else:
            if period_start > entry_start or period_stop > entry_stop:
                overlapping_entries.append(entry)

    return overlapping_entries


def calculate_charging_cost_for_period(rate_plans, plan_name, season, day_type, period_start, period_stop, required_hours):
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
    # print("overlapping_entries", overlapping_entries)
    
    for entry in overlapping_entries:
        if remaining_hours <= 0:
            break

        entry_start = entry['start_time']
        entry_stop = entry['stop_time']
        entry_rate = entry['rate']
        entry_tou_name = entry["tou_name"]

        entry_start_dt = datetime.combine(datetime.today(), entry_start)
        entry_stop_dt = datetime.combine(datetime.today(), entry_stop)
        period_start_dt = datetime.combine(datetime.today(), period_start)
        period_stop_dt = datetime.combine(datetime.today(), period_stop)

        # TODO Refactor, lots of copy paste code below
        reverse_period = period_stop < period_start
        # 16:00 - 8:00 am, 12:am - 3pm
        if reverse_period:
            if period_stop > entry_start:
                time_difference = period_stop_dt - entry_start_dt
                if time_difference > timedelta(0):
                    charging_time_in_period = min(time_difference.total_seconds() / 3600, remaining_hours)
                    remaining_hours -= charging_time_in_period
                    charging_details.append({
                        "period": f"{entry_start.strftime('%I:%M %p')} - {period_stop.strftime('%I:%M %p')}",
                        "hours": charging_time_in_period,
                        "cost": charging_time_in_period * entry_rate,
                        "tou_name": entry_tou_name
                    })
            elif period_start < entry_stop:
                time_difference = entry_start_dt - period_stop_dt
                if time_difference > timedelta(0):
                    charging_time_in_period = min(time_difference.total_seconds() / 3600, remaining_hours)
                    remaining_hours -= charging_time_in_period
                    charging_details.append({
                        "period": f"{entry_start.strftime('%I:%M %p')} - {period_stop.strftime('%I:%M %p')}",
                        "hours": charging_time_in_period,
                        "cost": charging_time_in_period * entry_rate,
                        "tou_name": entry_tou_name
                    })
                
        # 9am - 11pm, 12am -3pm
        else:
            if period_start > entry_start:
                time_difference = period_start_dt - entry_start_dt
                if time_difference > timedelta(0):
                    charging_time_in_period = min(time_difference.total_seconds() / 3600, remaining_hours)
                    remaining_hours -= charging_time_in_period
                    charging_details.append({
                        "period": f"{entry_start.strftime('%I:%M %p')} - {period_stop.strftime('%I:%M %p')}",
                        "hours": charging_time_in_period,
                        "cost": charging_time_in_period * entry_rate,
                        "tou_name": entry_tou_name
                    })
            elif period_stop > entry_stop:
                time_difference = period_stop_dt - entry_stop_dt
                if time_difference > timedelta(0):
                    charging_time_in_period = min(time_difference.total_seconds() / 3600, remaining_hours)
                    remaining_hours -= charging_time_in_period
                    charging_details.append({
                        "period": f"{entry_start.strftime('%I:%M %p')} - {period_stop.strftime('%I:%M %p')}",
                        "hours": charging_time_in_period,
                        "cost": charging_time_in_period * entry_rate,
                        "tou_name": entry_tou_name
                    })

    return charging_details


def simulate_charging_costs(rate_plans, driver_profiles, required_hours_per_day):
    """Simulate charging costs for each profile across all Plan Names over a two-day period."""
    charging_costs = defaultdict(lambda: defaultdict(list))

    for plan_name in rate_plans.keys():
        for profile_name, profile_data in driver_profiles.items():
            total_cost_for_two_days = 0.0
            charging_details = []

            for _ in range(DAYS_OF_CHARGING):
                charging_start_time = datetime.strptime(profile_data["Charging Hours Start"], "%I:%M %p").time()
                charging_end_time = datetime.strptime(profile_data["Charging Hours End"], "%I:%M %p").time()

                daily_charging_details = calculate_charging_cost_for_period(
                    rate_plans, plan_name, SUMMER_SEASON, DAY_TYPE, charging_start_time, charging_end_time, required_hours_per_day
                )
                total_cost_for_two_days += sum(entry['cost'] for entry in charging_details)

                charging_details.extend(daily_charging_details)

            charging_costs[profile_name][plan_name] = {
                "total_cost": total_cost_for_two_days,
                "charging_details": charging_details
            }
    return charging_costs

def print_charging_costs(charging_costs):
    """Print the total charging costs and detailed periods by TOU for each driver profile and plan name."""
    print("Charging Costs and Detailed Periods by TOU for Each Driver Profile and Plan Name:")
    output_rows = []
    
    for profile_name, plans in charging_costs.items():
        print(f"\n{profile_name}:")
        for plan_name, cost_data in plans.items():
            print(f"  Plan: {plan_name}")
            print(f"    Total Cost for Two Days: ${cost_data['total_cost']:.2f}")

            for detail in cost_data["charging_details"]:
                print(f"      Period: {detail['period']}, Hours: {detail['hours']:.2f}, Cost: ${detail['cost']:.2f}, TOU: {detail['tou_name']}")
                output_rows.append({
                    "Profile": profile_name,
                    "Plan": plan_name,
                    "Period": detail["period"],
                    "Hours": detail["hours"],
                    "Cost": detail["cost"],
                    "TOU": detail["tou_name"]
                })

    # Output to CSV
    output_df = pd.DataFrame(output_rows)
    output_df.to_csv(OUTPUT_CSV_FILE, index=False)
    print(f"\nResults have been saved to {OUTPUT_CSV_FILE}")

def main():
    # Load assumptions and rate data
    assumptions = load_assumptions()
    rate_plans = load_rate_data()
    
    # Extract assumptions
    average_commute_distance_miles = assumptions["average_commute_distance_miles"]
    kwh_per_mile = assumptions["kwh_per_mile"]
    charger_kw = assumptions["charger_kw"]
    driver_profiles = assumptions["driver_profiles"]

    # Calculate the daily charging needs in kWh and hours
    daily_energy_kwh = average_commute_distance_miles * kwh_per_mile * 2  # round-trip
    required_hours_per_day = daily_energy_kwh / charger_kw

    # Simulate charging costs over two days
    charging_costs = simulate_charging_costs(rate_plans, driver_profiles, required_hours_per_day)

    # Print and save the results
    print_charging_costs(charging_costs)

# Run the main function
if __name__ == "__main__":
    main()
