from abc import ABC, abstractmethod

from core.models import Offer
from core.health import SupplierCapabilities


class Supplier(ABC):
    name: str

    capabilities = SupplierCapabilities()

    @abstractmethod
    def lookup(
        self,
        isbn: str,
    ) -> list[Offer]:
        pass