from flask import Flask, jsonify, request
from flask_restful import Api, Resource
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_caching import Cache
from uuid import uuid4, UUID
from models import db, Flight, Passenger
from datetime import datetime


# Importing db and models
from models import db, Flight, Passenger



app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///flight.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['CACHE_TYPE'] = 'simple'  # Set up caching
cache = Cache(config={'CACHE_TYPE': 'SimpleCache'})  # Using the full path to backend classes directly
cache.init_app(app)


db.init_app(app)
api = Api(app)
migrate = Migrate(app, db)

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'message': 'The requested resource was not found.'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'message': 'An internal server error occurred.'}), 500

# Resources

class FlightResource(Resource):
    @cache.cached(timeout=120)
    def get(self, flight_id=None):
        try:
            if flight_id:
                flight = db.session.get(Flight, str(flight_id))
                if not flight:
                    return {'message': 'Flight not found'}, 404
                return flight.to_dict(), 200
            else:
                flights = Flight.query.all()
                return [flight.to_dict() for flight in flights], 200
        except Exception as e:
            return {'message': f'An error occurred while fetching flights: {str(e)}'}, 500

    def post(self):
        data = request.get_json()

        # Retrieve all fields from the request data
        flight_id = data.get('id')
        flight_name = data.get('flight_name')
        origin = data.get('origin')
        destination = data.get('destination')
        cost = data.get('cost')
        created_at = data.get('created_at')
        deleted_at = data.get('deleted_at')

        # Generate a new UUID if 'id' is not provided
        if not flight_id:
            flight_id = str(uuid4())

        # Validate the provided 'id'
        try:
            flight_id = str(UUID(flight_id))  # Validate flight_id format
        except ValueError:
            return {'message': 'Invalid flight ID format'}, 400

        # Check if all required fields are present
        if not flight_name or not origin or not destination or cost is None:
            return {'message': 'All fields (flight_name, origin, destination, cost) are required.'}, 400

        # Convert 'created_at' and 'deleted_at' to datetime objects if provided
        try:
            if created_at:
                created_at = datetime.fromisoformat(created_at)
            if deleted_at:
                deleted_at = datetime.fromisoformat(deleted_at)
        except ValueError:
            return {'message': 'Invalid datetime format. Use ISO 8601 format.'}, 400

        # Create a new Flight instance
        flight = Flight(
            id=flight_id,
            created_at=created_at,
            deleted_at=deleted_at,
            flight_name=flight_name,
            origin=origin,
            destination=destination,
            cost=cost
        )

        try:
            db.session.add(flight)
            db.session.commit()
            return flight.to_dict(), 201
        except Exception as e:
            db.session.rollback()
            return {'message': f'Error occurred: {str(e)}'}, 500



class PassengerResource(Resource):
    @cache.cached(timeout=120, query_string=True)
    def get(self, passenger_id=None):
        try:
            if passenger_id:
                passenger = db.session.get(Passenger, str(passenger_id))
                if not passenger:
                    return {'message': 'Passenger not found'}, 404
                return passenger.to_dict(), 200
            else:
                passengers = Passenger.query.filter(Passenger.deleted_at.is_(None)).all()
                return [passenger.to_dict() for passenger in passengers], 200
        except Exception as e:
            return {'message': f'An error occurred while fetching passengers: {str(e)}'}, 500


    def post(self):
        data = request.get_json()
        flight_id = data.get('flight_id')
        try:
            flight_id = str(UUID(flight_id))
        except ValueError:
            return {'message': 'Invalid flight ID format'}, 400
        
        flight = Flight.query.filter_by(id=flight_id).first()
        if not flight:
            return {'message': 'Flight not found'}, 404
        
        passenger = Passenger(
            name=data.get('name'),
            email=data.get('email'),
            flight=flight,
        )
        db.session.add(passenger)
        db.session.commit()
        return passenger.to_dict(), 201


    def put(self, passenger_id):
        try:
            passenger = db.session.get(Passenger, str(passenger_id))
            if not passenger:
                return {'message': 'Passenger not found'}, 404
            data = request.get_json()
            passenger.name = data.get('name', passenger.name)
            passenger.email = data.get('email', passenger.email)
            passenger.checked_in = data.get('checked_in', passenger.checked_in)
            db.session.commit()
            return passenger.to_dict(), 200
        except Exception as e:
            db.session.rollback()
            return {'message': f'An error occurred while updating the passenger: {str(e)}'}, 500




class PassengerSoftDeleteResource(Resource):
    def delete(self, passenger_id):
        try:
            passenger = db.session.get(Passenger, str(passenger_id))
            if not passenger:
                return {'message': 'Passenger not found'}, 404
            
            passenger.soft_delete()
            db.session.commit()
            return {'message': 'Passenger soft deleted'}, 200

        except Exception as e:
            db.session.rollback()
            return {'message': f'An error occurred while soft deleting the passenger: {str(e)}'}, 500


class PassengerRestoreResource(Resource):
    def patch(self, passenger_id):
        try:
            passenger = db.session.get(Passenger, str(passenger_id))
            if not passenger:
                return {'message': 'Passenger not found'}, 404
            
            if passenger.deleted_at is None:
                return {'message': 'Passenger is not soft deleted'}, 400
            
            passenger.restore()
            db.session.commit()
            return {'message': 'Passenger restored'}, 200

        except Exception as e:
            db.session.rollback()
            return {'message': f'An error occurred while restoring the passenger: {str(e)}'}, 500
        


class CheapestRouteResource(Resource):
    def get(self):
        try:
            # Parse request arguments
            origin = request.args.get('origin')
            destination = request.args.get('destination')

            if not origin or not destination:
                return {'message': 'Both origin and destination are required.'}, 400

            # Call the find_cheapest_route static method
            route, total_cost = Flight.find_cheapest_route(origin, destination)

            if route is None:
                return {'message': 'No route found between the specified points.'}, 404

            # Prepare route information for the response
            route_info = [flight.to_dict() for flight in route]
            return {'route': route_info, 'total_cost': total_cost}, 200

        except Exception as e:
            # Catch any unexpected errors
            return {'message': f'An unexpected error occurred: {str(e)}'}, 500


# Add resources to the API
api.add_resource(FlightResource, '/flights', '/flights/<uuid:flight_id>')
api.add_resource(PassengerResource, '/passengers', '/passengers/<uuid:passenger_id>')
api.add_resource(PassengerSoftDeleteResource, '/passengers/<uuid:passenger_id>/soft_delete')
api.add_resource(PassengerRestoreResource, '/passengers/<uuid:passenger_id>/restore')
api.add_resource(CheapestRouteResource, '/flights/cheapest_route')


# Run the app
if __name__ == '__main__':
    app.run(debug=True)
