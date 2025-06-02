from dotenv import load_dotenv
from typing import Optional
from amadeus import ResponseError, Client
import os
import format_flights


load_dotenv()


# Initialize Amadeus client
amadeus = Client(
    client_id=os.getenv('AMADEUS_API_KEY'),
    client_secret=os.getenv('AMADEUS_API_SECRET')
)

def verify_price(flight_id):
    try:
        # Flight offers pricing
        pricing_response = amadeus.shopping.flight_offers.pricing.post(
            flight_id  # Using the first flight offer from search
        )
        priced_offer = pricing_response.data
        return priced_offer
    except ResponseError as error:
        print(error)


def format_flight_results(flights):
    """Format flight results for display"""
    if not flights:
        return "No flights found matching your criteria."
    
    formatted = []
    for idx, flight in enumerate(flights[:5], 1):  # Show top 5 results
        itinerary = flight['itineraries'][0]
        segment = itinerary['segments'][0]
        price = flight['price']['total']
        
        formatted.append(
            f"{idx}. {segment['departure']['iataCode']} → {segment['arrival']['iataCode']}\n"
            f"   Departure: {segment['departure']['at']}\n"
            f"   Arrival: {segment['arrival']['at']}\n"
            f"   Airline: {segment['carrierCode']} {segment['aircraft']['code']}\n"
            f"   Price: {price} {flight['price']['currency']}\n"
            f"   Flight ID: {flight['id']}"
        )
    
    return "\n\n".join(formatted)
    

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
            params['nonStop'] = True 
        
        # Call Amadeus API
        response = amadeus.shopping.flight_offers_search.get(**params)
        
        # results
        return response.data
    
    except ResponseError as error:
        return f"Error searching flights: {error}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"




if __name__== "__main__":

    flights = search_flights("ADD","CDG","2025-06-20")
    print(format_flights.format_flight_results(flights))

    priced_offer = verify_price(flights[0])
    print(format_flights.format_price_verification(priced_offer))

   

