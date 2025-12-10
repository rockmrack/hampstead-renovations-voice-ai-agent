"""
Property service for postcode enrichment and property data lookup.
Auto-lookup property details when customer provides postcode.
"""

import httpx
import structlog
from config import settings
from models.conversation import PropertyData

logger = structlog.get_logger()


# North West London service areas
SERVICE_AREA_POSTCODES = ["NW3", "NW6", "NW11", "NW2", "NW8", "N6", "N2", "N10", "NW1", "NW5"]
SERVICE_AREA_DISTRICTS = [
    "Camden",
    "Barnet",
    "Brent",
    "Westminster",
    "Haringey",
    "Islington",
    "Hackney",
]


class PropertyService:
    """Service for property and postcode enrichment."""

    def __init__(self) -> None:
        self.epc_api_key = getattr(settings, "epc_api_key", None)
        self.postcodes_api_url = "https://api.postcodes.io/postcodes"
        self.epc_api_url = "https://epc.opendatacommunities.org/api/v1/domestic/search"

    async def lookup_postcode(self, postcode: str) -> dict | None:
        """
        Get basic postcode data from postcodes.io (free API).

        Args:
            postcode: UK postcode

        Returns:
            Dictionary with postcode data or None if invalid
        """
        clean_postcode = postcode.replace(" ", "").upper()

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.postcodes_api_url}/{clean_postcode}", timeout=10.0
                )

                if response.status_code == 200:
                    data = response.json()["result"]
                    return {
                        "postcode": data["postcode"],
                        "district": data.get("admin_district"),
                        "ward": data.get("admin_ward"),
                        "region": data.get("region"),
                        "latitude": data.get("latitude"),
                        "longitude": data.get("longitude"),
                        "in_london": data.get("region") == "London",
                        "outcode": data.get("outcode"),  # e.g., NW3
                    }

                logger.warning(
                    "postcode_lookup_failed", postcode=postcode, status=response.status_code
                )
                return None

        except Exception as e:
            logger.error("postcode_lookup_error", postcode=postcode, error=str(e))
            return None

    async def lookup_epc_data(
        self,
        postcode: str,
        address_hint: str | None = None,
    ) -> list[PropertyData]:
        """
        Get EPC data for properties at postcode.

        Args:
            postcode: UK postcode
            address_hint: Optional address to help match specific property

        Returns:
            List of PropertyData for properties at this postcode
        """
        if not self.epc_api_key:
            logger.info("epc_lookup_skipped_no_key", postcode=postcode)
            return []

        clean_postcode = postcode.replace(" ", "")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.epc_api_url,
                    params={"postcode": clean_postcode, "size": 100},
                    headers={
                        "Authorization": f"Basic {self.epc_api_key}",
                        "Accept": "application/json",
                    },
                    timeout=15.0,
                )

                if response.status_code != 200:
                    logger.warning(
                        "epc_lookup_failed", postcode=postcode, status=response.status_code
                    )
                    return []

                data = response.json()
                properties = []

                for row in data.get("rows", []):
                    properties.append(
                        PropertyData(
                            postcode=row.get("postcode"),
                            property_type=row.get("property-type"),
                            built_form=row.get("built-form"),
                            total_floor_area_sqm=(
                                float(row.get("total-floor-area"))
                                if row.get("total-floor-area")
                                else None
                            ),
                            construction_age=row.get("construction-age-band"),
                            current_energy_rating=row.get("current-energy-rating"),
                            potential_energy_rating=row.get("potential-energy-rating"),
                            local_authority=row.get("local-authority"),
                        )
                    )

                # If address hint provided, try to match
                if address_hint and properties:
                    address_lower = address_hint.lower()
                    for prop in properties:
                        if (
                            any(word in address_lower for word in ["flat", "apartment"])
                            and prop.property_type == "Flat"
                        ):
                            return [prop]

                return properties

        except Exception as e:
            logger.error("epc_lookup_error", postcode=postcode, error=str(e))
            return []

    def is_in_service_area(self, postcode_data: dict) -> bool:
        """
        Check if postcode is in Hampstead Renovations service area.

        Args:
            postcode_data: Data from postcode lookup

        Returns:
            True if in service area
        """
        outcode = postcode_data.get("outcode", "")
        district = postcode_data.get("district", "")

        return outcode in SERVICE_AREA_POSTCODES or district in SERVICE_AREA_DISTRICTS

    async def enrich_lead_with_property(
        self,
        postcode: str,
        address: str | None = None,
    ) -> dict:
        """
        Full enrichment for a lead based on postcode.

        Args:
            postcode: UK postcode
            address: Optional address details

        Returns:
            Enrichment dictionary with property information
        """
        # Get basic postcode data
        postcode_data = await self.lookup_postcode(postcode)

        if not postcode_data:
            return {"error": "Invalid postcode", "postcode": postcode}

        # Check if in service area
        in_service_area = self.is_in_service_area(postcode_data)

        # Get EPC data
        epc_properties = await self.lookup_epc_data(postcode, address)

        # Aggregate if multiple properties
        avg_sqm = None
        common_type = None
        common_age = None

        if epc_properties:
            sqm_values = [p.total_floor_area_sqm for p in epc_properties if p.total_floor_area_sqm]
            if sqm_values:
                avg_sqm = sum(sqm_values) / len(sqm_values)

            # Most common property type
            types = [p.property_type for p in epc_properties if p.property_type]
            if types:
                common_type = max(set(types), key=types.count)

            ages = [p.construction_age for p in epc_properties if p.construction_age]
            if ages:
                common_age = max(set(ages), key=ages.count)

        result = {
            "postcode": postcode_data["postcode"],
            "district": postcode_data.get("district"),
            "ward": postcode_data.get("ward"),
            "in_service_area": in_service_area,
            "typical_property_type": common_type,
            "typical_sqm": round(avg_sqm) if avg_sqm else None,
            "typical_age": common_age,
            "latitude": postcode_data.get("latitude"),
            "longitude": postcode_data.get("longitude"),
            "epc_data_available": len(epc_properties) > 0,
        }

        logger.info(
            "property_enrichment_complete",
            postcode=postcode,
            in_service_area=in_service_area,
            property_type=common_type,
        )

        return result

    def get_area_context(self, enrichment: dict) -> str:
        """
        Generate contextual description of area for conversation.

        Args:
            enrichment: Enrichment data from enrich_lead_with_property

        Returns:
            Natural language context string
        """
        parts = []

        if enrichment.get("district"):
            parts.append(f"in {enrichment['district']}")

        if not enrichment.get("in_service_area"):
            parts.append("(this is outside our primary service area)")
            return " ".join(parts)

        prop_type = enrichment.get("typical_property_type")
        if prop_type:
            type_descriptions = {
                "Detached": "detached properties",
                "Semi-Detached": "semi-detached houses",
                "Terraced": "terraced houses",
                "End-Terrace": "end-terrace properties",
                "Flat": "flats and apartments",
            }
            parts.append(f"- typically {type_descriptions.get(prop_type, prop_type.lower())}")

        age = enrichment.get("typical_age")
        if age:
            if "1900" in age or "Victorian" in age.lower():
                parts.append("with lovely Victorian character")
            elif "1930" in age or "Edwardian" in age.lower():
                parts.append("with Edwardian features")
            elif "1950" in age or "1960" in age:
                parts.append("from the mid-century period")

        sqm = enrichment.get("typical_sqm")
        if sqm:
            parts.append(f"(around {sqm}sqm on average)")

        return " ".join(parts)


# Singleton instance
property_service = PropertyService()
