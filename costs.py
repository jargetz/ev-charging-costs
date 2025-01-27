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
def sort_by_tou_duration_priority(entry):
    # Sort by TOU_PRIORITY first, then by overlap_duration numerically
    return (
        TOU_PRIORITY.get(entry["tou_name"], 3),  # Primary: TOU priority (default to 3)
        -entry["overlap_duration"]               # Secondary: Numeric overlap_duration
    )

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


def calculate_and_return_overlapping_charging_periods(
    rate_plans, plan_name, season, day_type, profile_charging_periods):
    """
    Retrieve all entries that overlap with a given start and stop time period.
    Modify in place entries with overlap duration > 0
    """
    overlapping_entries = []

    # Always include "All" as a day_type
    combined_rate_plans = rate_plans[plan_name][season][day_type] + rate_plans[plan_name][season][ALL]

    for entry in combined_rate_plans:
        entry_start = entry['start_time']
        entry_stop = entry['stop_time']
        entry_charging_times = []

        if entry_start > entry_stop:
            # Case: Crossing over midnight
            # Split into two intervals: Start to midnight and midnight to end
            if entry_stop == time(0, 0, 0):
               entry_charging_times = [(entry_start, time(23, 59, 59))]
            else:
                entry_charging_times = [(entry_start, time(23, 59, 59)), (time(0, 0, 0), entry_stop)]
        else:
            entry_charging_times = [(entry_start, entry_stop)]

        total_time = timedelta()  # Initialize total overlap time
        for charging_time_entry in entry_charging_times:
            charging_time_entry_start = charging_time_entry[0]
            charging_time_entry_stop = charging_time_entry[1]

            for profile_charging_period in profile_charging_periods:
                profile_charging_period_start = profile_charging_period[0]
                profile_charging_period_stop = profile_charging_period[1]

                # Convert time objects to datetime objects using a reference date
                reference_date = datetime.today()
                charging_time_entry_start_dt = datetime.combine(reference_date, charging_time_entry_start)
                charging_time_entry_stop_dt = datetime.combine(reference_date, charging_time_entry_stop)
                profile_charging_period_start_dt = datetime.combine(reference_date, profile_charging_period_start)
                profile_charging_period_stop_dt = datetime.combine(reference_date, profile_charging_period_stop)

                # Calculate the overlap
                overlap_start = max(charging_time_entry_start_dt, profile_charging_period_start_dt)  # Later of the two starts
                overlap_end = min(charging_time_entry_stop_dt, profile_charging_period_stop_dt)  # Earlier of the two ends

                # Check if there is an actual overlap
                if overlap_start < overlap_end:
                    # Add the overlap duration to the total
                    total_time += overlap_end - overlap_start
        if total_time.total_seconds() > 0:
            overlapping_entries.append(entry.update({"overlap_duration": total_time}) or entry)

    return overlapping_entries


def calculate_charging_cost_for_period(
        rate_plans,
        plan_name,
        season,
        day_type,
        charging_periods,
        required_hours,
        level,
        charging_speed):
    """
    Calculate the cost for charging within a single period, prioritizing cheaper TOU periods:
    Super Off-Peak, then Off-Peak, and finally Peak if needed.
    """
    remaining_hours = required_hours
    charging_details = []

    overlapping_entries = calculate_and_return_overlapping_charging_periods(
        rate_plans, 
        plan_name, 
        season, 
        day_type, 
        charging_periods
    )
    overlapping_entries.sort(key=sort_by_tou_duration_priority)

    for entry in overlapping_entries:
        if remaining_hours <= 0:
            break
        entry_start_time = entry["start_time"]
        entry_stop_time = entry["stop_time"]

        charging_time_in_period = min(entry["overlap_duration"].total_seconds()/3600, remaining_hours)
        remaining_hours -= charging_time_in_period
        charging_details.append({
            "period": f"{entry_start_time.strftime('%I:%M %p')} - {entry_stop_time.strftime('%I:%M %p')}",
            "hours": charging_time_in_period,
            "cost": charging_time_in_period * entry["rate"] * charging_speed,
            "tou_name": entry["tou_name"],
            "level": level
        })

    # Combine all entries with the same period, tou_name, and level. I could in theory
    # leave it to indicate that it crosses midnight, but this seems less confusing.
    # In the future if we wanted to know about midnight crossover we could reconfigure this
    combined_details = defaultdict(lambda: {"hours": 0, "cost": 0.0})

    for entry in charging_details:
        key = (entry["period"], entry["tou_name"], entry["level"])  # Grouping key
        combined_details[key]["hours"] += entry["hours"]  # Aggregate hours
        combined_details[key]["cost"] += entry["cost"]  # Aggregate cost

    # Convert combined details back to a list of dictionaries
    final_charging_details = [
        {
            "period": k[0], 
            "tou_name": k[1], 
            "level": k[2], 
            "hours": round(v["hours"], 2), 
            "cost": round(v["cost"], 2)
        }
        for k, v in combined_details.items()
    ]
    return final_charging_details


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

            # Don't deal with hours crossing over midnight, just split it apart,
            # e.g. 8pm - 7am => 8pm-12am, 12am-7am
            for _ in range(DAYS_OF_CHARGING):
                charging_hours_for_profile = split_charging_hours(profile_data)

                daily_charging_details = calculate_charging_cost_for_period(
                    rate_plans, 
                    plan_name,
                    SUMMER_SEASON, 
                    DAY_TYPE,
                    charging_hours_for_profile,
                    required_hours_per_day_level_2,
                    "2",
                    charger_kw_level_2,
                )
       
                charging_details.extend(daily_charging_details)
                total_cost_for_two_days_level_2 += sum(entry['cost'] for entry in charging_details)

                if required_hours_per_day_level_1 <= 24:
                    daily_charging_details_l1 = calculate_charging_cost_for_period(
                        rate_plans, plan_name,
                        SUMMER_SEASON, 
                        DAY_TYPE,
                        charging_hours_for_profile,
                        required_hours_per_day_level_1,
                        "1",
                        charger_kw_level_1
                    )
                    charging_details.extend(daily_charging_details_l1)
                    total_cost_for_two_days_level_1 += sum(entry['cost'] for entry in charging_details) 

            charging_costs[profile_name][plan_name] = {
                "total_cost_level_2": total_cost_for_two_days_level_2,
                "total_cost_level_1": total_cost_for_two_days_level_1,
                "charging_details": charging_details
            }
    return charging_costs


def split_charging_hours(profile_data):
    # Parse start and end times
    charging_start_time = datetime.strptime(profile_data["Charging Hours Start"], "%I:%M %p").time()
    charging_end_time = datetime.strptime(profile_data["Charging Hours End"], "%I:%M %p").time()
    
    if charging_start_time < charging_end_time:
        # Case: No crossing over midnight
        return [(charging_start_time, charging_end_time)]
    else:
        # Case: Crossing over midnight
        # Split into two intervals: Start to midnight and midnight to end
        return [(charging_start_time, time(23, 59, 59)), (time(0, 0, 0), charging_end_time)]
    

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
