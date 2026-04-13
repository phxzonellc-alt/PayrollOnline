import requests
import sys
from datetime import datetime

class PayrollAPITester:
    def __init__(self, base_url="https://payroll-excel-1.preview.emergentagent.com"):
        self.base_url = base_url
        self.session = requests.Session()
        self.tests_run = 0
        self.tests_passed = 0
        self.event_id = None
        self.employee_ids = []

    def run_test(self, name, method, endpoint, expected_status, data=None, files=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = self.session.get(url)
            elif method == 'POST':
                if files:
                    response = self.session.post(url, files=files)
                else:
                    response = self.session.post(url, json=data)
            elif method == 'PUT':
                response = self.session.put(url, json=data)
            elif method == 'DELETE':
                response = self.session.delete(url)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return True, response.json() if response.content else {}
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    print(f"   Response: {response.text}")
                except:
                    pass
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_login(self):
        """Test admin login"""
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "auth/login",
            200,
            data={"email": "admin@example.com", "password": "admin123"}
        )
        if success:
            print(f"   Logged in as: {response.get('email', 'Unknown')}")
        return success

    def test_auth_me(self):
        """Test getting current user"""
        success, response = self.run_test(
            "Get Current User",
            "GET",
            "auth/me",
            200
        )
        return success

    def test_create_event(self):
        """Test creating a new event"""
        event_data = {
            "event_name": "Test Event",
            "job_number": "1001",
            "employer": "ACME Corp",
            "venue": "Convention Center",
            "payroll_name": "Test Payroll",
            "contact_email": "test@example.com",
            "cell_phone": "555-1234"
        }
        success, response = self.run_test(
            "Create Event",
            "POST",
            "events",
            200,
            data=event_data
        )
        if success and 'id' in response:
            self.event_id = response['id']
            print(f"   Created event with ID: {self.event_id}")
        return success

    def test_get_events(self):
        """Test listing events"""
        success, response = self.run_test(
            "List Events",
            "GET",
            "events",
            200
        )
        if success:
            print(f"   Found {len(response)} events")
        return success

    def test_get_event(self):
        """Test getting specific event"""
        if not self.event_id:
            print("❌ No event ID available for testing")
            return False
            
        success, response = self.run_test(
            "Get Event Details",
            "GET",
            f"events/{self.event_id}",
            200
        )
        return success

    def test_add_employees(self):
        """Test adding employees to event"""
        if not self.event_id:
            print("❌ No event ID available for testing")
            return False

        employees = [
            {"name": "John Doe", "dept_emp_num": "101", "rate1": 25, "rate2": 30, "special_rate": 15},
            {"name": "Jane Smith", "dept_emp_num": "102", "rate1": 28, "rate2": 35, "special_rate": 20}
        ]
        
        all_success = True
        for emp in employees:
            success, response = self.run_test(
                f"Add Employee: {emp['name']}",
                "POST",
                f"events/{self.event_id}/employees",
                200,
                data=emp
            )
            if success and 'id' in response:
                self.employee_ids.append(response['id'])
                print(f"   Added employee with ID: {response['id']}")
            all_success = all_success and success
        
        return all_success

    def test_get_employees(self):
        """Test getting employees for event"""
        if not self.event_id:
            print("❌ No event ID available for testing")
            return False
            
        success, response = self.run_test(
            "Get Employees",
            "GET",
            f"events/{self.event_id}/employees",
            200
        )
        if success:
            print(f"   Found {len(response)} employees")
        return success

    def test_time_entries(self):
        """Test adding time entries for Day 1"""
        if not self.event_id or not self.employee_ids:
            print("❌ No event ID or employee IDs available for testing")
            return False

        # Test time entries for Day 1
        # John Doe: ST R1=8, OT R1=2
        # Jane Smith: ST R2=6, OT R2=3
        entries = [
            {
                "employee_id": self.employee_ids[0],
                "day_number": 1,
                "st_r1": 8,
                "ot_r1": 2,
                "dt_r1": 0,
                "st_r2": 0,
                "ot_r2": 0,
                "dt_r2": 0,
                "sr_hours": 0
            },
            {
                "employee_id": self.employee_ids[1],
                "day_number": 1,
                "st_r1": 0,
                "ot_r1": 0,
                "dt_r1": 0,
                "st_r2": 6,
                "ot_r2": 3,
                "dt_r2": 0,
                "sr_hours": 0
            }
        ]

        success, response = self.run_test(
            "Batch Update Time Entries",
            "POST",
            f"events/{self.event_id}/time-entries/batch",
            200,
            data={"entries": entries}
        )
        return success

    def test_daily_statement(self):
        """Test getting daily statement for Day 1"""
        if not self.event_id:
            print("❌ No event ID available for testing")
            return False
            
        success, response = self.run_test(
            "Get Daily Statement Day 1",
            "GET",
            f"events/{self.event_id}/daily-statement/1",
            200
        )
        
        if success and 'employees' in response:
            print("   Verifying payroll calculations...")
            employees = response['employees']
            
            # Verify John Doe's calculation: 25*8 + 25*1.5*2 = 200 + 75 = 275
            john = next((emp for emp in employees if 'John' in emp.get('name', '')), None)
            if john:
                expected_gross = 275.0
                actual_gross = john.get('gross', 0)
                if abs(actual_gross - expected_gross) < 0.01:
                    print(f"   ✅ John Doe gross calculation correct: ${actual_gross}")
                else:
                    print(f"   ❌ John Doe gross calculation incorrect: expected ${expected_gross}, got ${actual_gross}")
                    
            # Verify Jane Smith's calculation: 35*6 + 35*1.5*3 = 210 + 157.5 = 367.5
            jane = next((emp for emp in employees if 'Jane' in emp.get('name', '')), None)
            if jane:
                expected_gross = 367.5
                actual_gross = jane.get('gross', 0)
                if abs(actual_gross - expected_gross) < 0.01:
                    print(f"   ✅ Jane Smith gross calculation correct: ${actual_gross}")
                else:
                    print(f"   ❌ Jane Smith gross calculation incorrect: expected ${expected_gross}, got ${actual_gross}")
        
        return success

    def test_sum_totals(self):
        """Test getting sum totals"""
        if not self.event_id:
            print("❌ No event ID available for testing")
            return False
            
        success, response = self.run_test(
            "Get Sum Totals",
            "GET",
            f"events/{self.event_id}/sum-totals",
            200
        )
        
        if success and 'employees' in response:
            print(f"   Found {len(response['employees'])} employees in summary")
        
        return success

    def test_export_excel(self):
        """Test Excel export"""
        if not self.event_id:
            print("❌ No event ID available for testing")
            return False
            
        success, _ = self.run_test(
            "Export Excel",
            "GET",
            f"events/{self.event_id}/export/excel",
            200
        )
        return success

    def test_export_pdf(self):
        """Test PDF export"""
        if not self.event_id:
            print("❌ No event ID available for testing")
            return False
            
        success, _ = self.run_test(
            "Export PDF",
            "GET",
            f"events/{self.event_id}/export/pdf",
            200
        )
        return success

    def test_update_employee(self):
        """Test updating employee information (inline editing)"""
        if not self.event_id or not self.employee_ids:
            print("❌ No event ID or employee IDs available for testing")
            return False
            
        # Update first employee (John Doe)
        update_data = {
            "name": "John Doe Updated",
            "dept_emp_num": "101-UPDATED", 
            "rate1": 27,  # Changed from 25
            "rate2": 32,  # Changed from 30
            "special_rate": 18  # Changed from 15
        }
        
        success, response = self.run_test(
            "Update Employee (Inline Edit)",
            "PUT",
            f"events/{self.event_id}/employees/{self.employee_ids[0]}",
            200,
            data=update_data
        )
        
        if success:
            print(f"   Updated employee name: {response.get('name', 'Unknown')}")
            print(f"   Updated rate1: ${response.get('rate1', 0)}")
        
        return success

    def test_bulk_import_csv(self):
        """Test bulk employee import from CSV"""
        if not self.event_id:
            print("❌ No event ID available for testing")
            return False
            
        # Create a test CSV content
        csv_content = """Name,Dept/Emp Number,Rate 1,Rate 2,Special Rate
Test Worker,300,20,25,10
Another Worker,301,22,27,12"""
        
        # Create a file-like object for the CSV
        files = {'file': ('test_employees.csv', csv_content, 'text/csv')}
        
        success, response = self.run_test(
            "Bulk Import CSV",
            "POST",
            f"events/{self.event_id}/employees/import",
            200,
            files=files
        )
        
        if success:
            imported_count = response.get('imported', 0)
            print(f"   Imported {imported_count} employees from CSV")
            if 'employees' in response:
                for emp in response['employees']:
                    self.employee_ids.append(emp['id'])
        
        return success

    def test_daily_statement_pdf(self):
        """Test daily statement PDF export for Day 1"""
        if not self.event_id:
            print("❌ No event ID available for testing")
            return False
            
        success, _ = self.run_test(
            "Export Daily Statement PDF Day 1",
            "GET",
            f"events/{self.event_id}/daily-statement/1/pdf",
            200
        )
        return success

    def test_employee_template_download(self):
        """Test CSV template download"""
        success, _ = self.run_test(
            "Download Employee CSV Template",
            "GET",
            "employees/template",
            200
        )
        return success

    def test_logout(self):
        """Test logout"""
        success, response = self.run_test(
            "Logout",
            "POST",
            "auth/logout",
            200
        )
        return success

def main():
    print("🚀 Starting Payroll System API Tests")
    print("=" * 50)
    
    tester = PayrollAPITester()
    
    # Run authentication tests
    if not tester.test_login():
        print("❌ Login failed, stopping tests")
        return 1
    
    if not tester.test_auth_me():
        print("❌ Auth verification failed")
        return 1
    
    # Run event management tests
    if not tester.test_create_event():
        print("❌ Event creation failed")
        return 1
    
    if not tester.test_get_events():
        print("❌ Event listing failed")
        return 1
    
    if not tester.test_get_event():
        print("❌ Event retrieval failed")
        return 1
    
    # Run employee management tests
    if not tester.test_add_employees():
        print("❌ Employee creation failed")
        return 1
    
    if not tester.test_get_employees():
        print("❌ Employee listing failed")
        return 1
    
    # Run time entry tests
    if not tester.test_time_entries():
        print("❌ Time entry creation failed")
        return 1
    
    if not tester.test_daily_statement():
        print("❌ Daily statement failed")
        return 1
    
    if not tester.test_sum_totals():
        print("❌ Sum totals failed")
        return 1
    
    # Test new features: inline editing and bulk import
    if not tester.test_update_employee():
        print("❌ Employee update (inline editing) failed")
        return 1
    
    if not tester.test_bulk_import_csv():
        print("❌ Bulk CSV import failed")
        return 1
    
    # Test new PDF and template features
    if not tester.test_daily_statement_pdf():
        print("❌ Daily statement PDF export failed")
        return 1
    
    if not tester.test_employee_template_download():
        print("❌ Employee template download failed")
        return 1
    
    # Run export tests
    if not tester.test_export_excel():
        print("❌ Excel export failed")
        return 1
    
    if not tester.test_export_pdf():
        print("❌ PDF export failed")
        return 1
    
    # Test logout
    if not tester.test_logout():
        print("❌ Logout failed")
        return 1
    
    # Print final results
    print("\n" + "=" * 50)
    print(f"📊 Tests completed: {tester.tests_passed}/{tester.tests_run} passed")
    
    if tester.tests_passed == tester.tests_run:
        print("🎉 All tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())