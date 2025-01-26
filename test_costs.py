import pandas as pd

def test_super_costs_output():
    # Run the costs.py script and capture its output
    output = pd.read_csv('charging_costs_over_one_day_super_commute.csv')  # assuming costs.py writes to output.csv

    # Load the expected output from SUPER_COMMUTE_TEST_OUTPUT.csv
    expected_output = pd.read_csv('SUPER_COMMUTE_TEST_OUTPUT.csv')

    try:
        test_data_equality(output, expected_output)
        pd.testing.assert_frame_equal(output, expected_output)
    except AssertionError as e:
        raise AssertionError(f"Super Commute Test: {str(e)}")  

def test_average_costs_output():
    # Run the costs.py script and capture its output
    output = pd.read_csv('charging_costs_over_one_day_average_commute.csv')  # assuming costs.py writes to output.csv

    expected_output = pd.read_csv('AVERAGE_COMMUTE_TEST_OUTPUT.csv')

    try:
        test_data_equality(output, expected_output)
        pd.testing.assert_frame_equal(output, expected_output)
    except AssertionError as e:
        raise AssertionError(f"Average Commute Test: {str(e)}")  


def test_data_equality(output, expected_output):
    output_dict = convert_to_dict(output)
    expected_output_dict = convert_to_dict(expected_output)
    compare_nested_dicts(expected_output_dict, output_dict)


def convert_to_dict(df):
    # Group by the required keys
    grouped = df.groupby(['Profile', 'Plan', 'TOU'], group_keys=False)
    
    # Create the nested dictionary with rounding to 2 decimal places
    nested_dict = grouped.apply(
        lambda group: [
            (
                round(row[0], 2),  # Round 'Hours'
                round(row[1], 2),  # Round 'Cost'
                row[2],            # 'Period'
                row[3]             # 'Level'
            )
            for row in group.loc[:, ['Hours', 'Cost', 'Period', 'Level']].itertuples(index=False, name=None)
        ]
    ).to_dict()
    
    return nested_dict


def compare_nested_dicts(expected_output_dict, output_dict):
    for key, expected_value in expected_output_dict.items():
        if key not in output_dict:
            raise AssertionError(f"Key {key} is missing in output_dict.")
        
        output_value = output_dict[key]
        
        # Check if both are lists of tuples and have the same length
        if not isinstance(output_value, list) or not isinstance(expected_value, list):
            raise AssertionError(f"Value for key {key} should be a list of tuples.")
        
        if len(expected_value) != len(output_value):
            raise AssertionError(
                f"Mismatch in number of tuples for key {key}: "
                f"expected {len(expected_value)}, got {len(output_value)}."
            )
        
        # Compare each tuple in the list
        for idx, (exp, out) in enumerate(zip(expected_value, output_value)):
            if exp != out:
                raise AssertionError(
                    f"Mismatch in tuple {idx} for key {key}: "
                    f"expected {exp}, got {out}."
                )
    print("All keys and values match!")


if __name__ == '__main__':
    print("Comparing to expected output...")
    test_super_costs_output()
    test_average_costs_output()
    print("Testing Completed.")