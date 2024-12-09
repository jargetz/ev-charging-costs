import pandas as pd

def test_costs_output():
    # Run the costs.py script and capture its output
    output = pd.read_csv('charging_costs_over_one_day.csv')  # assuming costs.py writes to output.csv

    # Load the expected output from SUPER_COMMUTE_TEST_OUTPUT.csv
    expected_output = pd.read_csv('SUPER_COMMUTE_TEST_OUTPUT.csv')

    # Compare the two dataframes
    pd.testing.assert_frame_equal(output, expected_output)


if __name__ == '__main__':
    test_costs_output()