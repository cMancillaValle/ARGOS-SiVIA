from dotenv import load_dotenv
load_dotenv()

from backend.services.two_factor import check_availability

print(check_availability())