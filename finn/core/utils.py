class BAPItemError(Exception):
    """Custom exception for BAPItem errors."""
    
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return f"BAPItemError: {self.message}"