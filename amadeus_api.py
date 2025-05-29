from dotenv import load_dotenv
from typing import Optional
from amadeus import ResponseError, Client
import os


load_dotenv()


# Initialize Amadeus client
amadeus = Client(
    client_id=os.getenv('AMADEUS_API_KEY'),
    client_secret=os.getenv('AMADEUS_API_SECRET')
)


def search_flights(
    departure: str, 
    destination: str, 
    date: str, 
    passengers: int = 1,
    return_date: Optional[str] = None
) -> str:
    """Search for available flights between airports on specific dates.
    
    Args:
        departure: IATA code of departure airport (e.g. 'JFK')
        destination: IATA code of destination airport (e.g. 'LHR')
        date: Departure date in YYYY-MM-DD format
        passengers: Number of adult passengers (default 1)
        return_date: Optional return date for round trips (YYYY-MM-DD)
    
    Returns:
        Formatted string with flight options or error message
    """
    try:
        # Build search parameters
        params = {
            'originLocationCode': departure,
            'destinationLocationCode': destination,
            'departureDate': date,
            'adults': passengers
        }
        
        if return_date:
            params['returnDate'] = return_date
            params['nonStop'] = True  # Example additional parameter
        
        # Call Amadeus API
        response = amadeus.shopping.flight_offers_search.get(**params)
        
        # results
        return response.data
    
    except ResponseError as error:
        return f"Error searching flights: {error}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"


flights= search_flights("ADD","CDG","2025-06-10")
print(flights)
