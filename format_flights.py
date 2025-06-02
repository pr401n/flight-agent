def format_flight_results(flights):
    """Format flight results for display with enhanced details"""
    if not flights:
        return "No flights found matching your criteria."
    
    formatted = []
    for idx, flight in enumerate(flights[:5], 1):  # Show top 5 results
        # Airline and pricing info
        airline_codes = flight['validatingAirlineCodes']
        price = flight['price']['total']
        currency = flight['price']['currency']
        
        # Itinerary details
        itinerary_text = []
        for itinerary in flight['itineraries']:
            segments = itinerary['segments']
            duration = itinerary['duration'][2:].lower()  # Convert PT4H5M to 4h5m
            
            segment_details = []
            for seg in segments:
                stops = "Nonstop" if seg['numberOfStops'] == 0 else f"{seg['numberOfStops']} stop(s)"
                
                segment_details.append(
                    f"  ✈️ {seg['departure']['iataCode']} → {seg['arrival']['iataCode']} "
                    f"(Airline: {get_airline_name(seg['carrierCode'])}) "
                    f"| Flight {seg['carrierCode']}{seg['number']}\n"
                    f"  🕒 Depart: {format_time(seg['departure']['at'])} "
                    f"| Arrive: {format_time(seg['arrival']['at'])}\n"
                    f"  ⏱ Duration: {format_duration(seg['duration'])} "
                    f"| {stops} | Aircraft: {seg['aircraft']['code']}\n"
                    f"  🛄 Baggage: {get_baggage_info(flight, seg['id'])}"
                )
            
            itinerary_text.append(
                f"🔹 Itinerary ({duration}):\n" + 
                "\n".join(segment_details)
            )
        
        formatted.append(
            f"{idx}. {' + '.join(airline_codes)} Flight\n"
            f"💰 Price: {price} {currency} (Base: {flight['price']['base']} + Taxes: {float(price)-float(flight['price']['base']):.2f})\n" +
            "\n".join(itinerary_text) +
            f"\n📝 Last ticket date: {flight.get('lastTicketingDate', 'N/A')}" +
            f"\n🆔 Offer ID: {flight['id']}"
        )
    
    return "\n\n" + "━"*50 + "\n\n".join(formatted) + "\n" + "━"*50

def format_price_verification(priced_offer):
    """Format the priced offer verification response with error handling"""
    if not priced_offer or 'flightOffers' not in priced_offer:
        return "No valid pricing information available."
    
    try:
        flight = priced_offer['flightOffers'][0]
        price = flight['price']
        requirements = priced_offer.get('bookingRequirements', {})
        
        # Traveler pricing details with safe key access
        traveler_info = []
        for traveler in flight.get('travelerPricings', []):
            fare_details = []
            for segment in traveler.get('fareDetailsBySegment', []):
                segment_text = [
                    f"  - Segment {segment.get('segmentId', 'N/A')}:",
                    f"{segment.get('brandedFare', 'Standard')} fare" if 'brandedFare' in segment else "Standard fare",
                    f"(Class: {segment.get('class', 'N/A')}," if 'class' in segment else "",
                    f"Basis: {segment.get('fareBasis', 'N/A')})" if 'fareBasis' in segment else ")"
                ]
                
                baggage_text = ""
                if 'includedCheckedBags' in segment and 'quantity' in segment['includedCheckedBags']:
                    baggage_text = f"\n    Includes: {segment['includedCheckedBags']['quantity']} checked bags"
                elif 'includedCheckedBags' in traveler:
                    baggage_text = f"\n    Includes: {traveler['includedCheckedBags']['quantity']} checked bags"
                
                fare_details.append(" ".join(filter(None, segment_text)) + baggage_text)
            
            traveler_text = [
                f"👤 Traveler {traveler.get('travelerId', 'N/A')}",
                f"({traveler.get('travelerType', 'UNKNOWN')}):",
                f"\n  💰 Total: {traveler['price']['total']} {traveler['price']['currency']}"
                if 'price' in traveler and 'total' in traveler['price'] else "",
                f"\n  🎟 Fare Details:\n" + "\n".join(fare_details) if fare_details else ""
            ]
            traveler_info.append(" ".join(filter(None, traveler_text)))
        
        # Booking requirements
        reqs = []
        if requirements.get('emailAddressRequired'):
            reqs.append("✓ Email address required")
        if requirements.get('mobilePhoneNumberRequired'):
            reqs.append("✓ Phone number required")
        if flight.get('instantTicketingRequired'):
            reqs.append("✓ Immediate payment required")
        if flight.get('paymentCardRequired'):
            reqs.append("✓ Credit card required")
        
        # Price breakdown
        price_breakdown = []
        if 'grandTotal' in price:
            price_breakdown.append(f"  - Total Price: {price['grandTotal']} {price.get('currency', '')}")
        if 'base' in price:
            tax_amount = float(price.get('total', 0)) - float(price['base'])
            price_breakdown.append(f"     (Base Fare: {price['base']} + Taxes: {tax_amount:.2f})")
        if 'refundableTaxes' in traveler.get('price', {}):
            price_breakdown.append(f"  - Refundable Taxes: {traveler['price']['refundableTaxes']}")
        
        return (
            "✅ PRICE VERIFICATION SUCCESSFUL\n" +
            "━"*50 + "\n" +
            f"✈️ Flight Summary:\n" +
            f"  - Airlines: {', '.join(flight.get('validatingAirlineCodes', ['N/A']))}\n" +
            "\n".join(price_breakdown) + "\n" +
            f"  - Last Ticketing Date: {flight.get('lastTicketingDate', 'N/A')}\n\n" +
            "📋 Booking Requirements:\n" +
            ("  " + "\n  ".join(reqs) if reqs else "  No special requirements") + "\n\n" +
            "🧳 Baggage Allowance:\n" +
            (f"  - {traveler['fareDetailsBySegment'][0]['includedCheckedBags']['quantity']} checked bags included\n\n"
             if traveler.get('fareDetailsBySegment') and traveler['fareDetailsBySegment'][0].get('includedCheckedBags')
             else "  - Baggage info not available\n\n") +
            "👥 Traveler Pricing Details:\n" +
            "\n".join(traveler_info) +
            "\n" + "━"*50
        )
    
    except Exception as e:
        return f"⚠️ Error formatting price verification: {str(e)}\nRaw data: {priced_offer}"
    
    
# Helper functions
def get_airline_name(code):
    """Convert airline code to name (you could expand this with a dictionary)"""
    airline_map = {
        'QR': 'Qatar Airways',
        'EK': 'Emirates',
        'AA': 'American Airlines',
        # Add more mappings as needed
    }
    return airline_map.get(code, code)

def format_time(datetime_str):
    """Format ISO datetime to readable time"""
    from datetime import datetime
    dt = datetime.fromisoformat(datetime_str)
    return dt.strftime("%a, %b %d %H:%M")

def format_duration(duration_str):
    """Convert PT4H5M to 4h 5m"""
    return duration_str[2:].replace('H', 'h ').replace('M', 'm').strip()

def get_baggage_info(flight, segment_id):
    """Get baggage allowance for specific segment"""
    for traveler in flight['travelerPricings']:
        for segment in traveler['fareDetailsBySegment']:
            if segment['segmentId'] == segment_id:
                return f"{segment['includedCheckedBags']['quantity']} checked bags"
    return "Baggage info not available"