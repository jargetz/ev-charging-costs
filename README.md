# EV Charging Cost Analysis

---

## Overview

This repository provides tools to analyze electric vehicle (EV) charging costs using publicly available rate data from Fall/Winter 2024. The rates used in this project are:
- **Applicable to weekday or all-time charging.**
- **Summer rates only.**

---

## Scripts

- **`test_costs.py`**:
  - Runs unit tests to compare actual output to expected results in pre-defined output sheets.
  - Useful for ensuring data accuracy and consistency.

  **Usage**:
  ```bash
  python test_costs.py
  ```

- **`costs.py`**:
  - Main script to generate EV charging cost calculations based on input data and rates.

  **Usage**:
  ```bash
  python costs.py
  ```

---

## Data Sources

The rates data used in this analysis are sourced from publicly available information collected during Fall/Winter 2024. The project is limited to:
- Rates that are applicable for **weekday** or **all-time charging**.
- **Summer rates** only.

---

## Requirements

- Python 3.8+
- Dependencies are listed in `requirements.txt`. Install them with:
  ```bash
  pip install -r requirements.txt
  ```

---

## License

This project is open-source and available under the MIT License. See the `LICENSE` file for more details.
