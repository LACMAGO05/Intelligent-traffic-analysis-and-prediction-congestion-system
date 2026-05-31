class CongestionIntelligence:
    @staticmethod
    def classify(duration_min, duration_traffic_min):
        """
        Classify congestion level based on:
        - traffic delay percentage
        - traffic duration increase
        """
        if duration_min <= 0:
            return "Low"
            
        ratio = duration_traffic_min / duration_min
        
        if ratio < 1.2:
            return "Low"
        elif ratio < 1.6:
            return "Medium"
        else:
            return "High"

    @staticmethod
    def get_score_contribution(congestion_level):
        mapping = {
            "Low": 0,
            "Medium": 20,
            "High": 40
        }
        return mapping.get(congestion_level, 0)
