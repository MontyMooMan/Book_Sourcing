from core.comparison import cheapest_offer

from suppliers.bookxcess import BookXcessSupplier
from suppliers.bookdelivery import BookDeliverySupplier
from suppliers.mph import MPHSupplier


def main():
    isbns = [
        "9781837251544",
    ]

    suppliers = [
        BookXcessSupplier(),
        BookDeliverySupplier(),
        MPHSupplier(),
    ]

    for isbn in isbns:
        print("\n" + "=" * 60)
        print(f"ISBN: {isbn}")
        print("=" * 60)

        offers = []

        for supplier in suppliers:
            print(f"Searching {supplier.name}...")

            offer = supplier.lookup(isbn)

            if offer:
                offers.append(offer)

                print(
                    f"  FOUND: {offer.title} | "
                    f"{offer.currency} {offer.price}"
                )
            else:
                print("  Not found.")

        best = cheapest_offer(offers)

        if best:
            print("\nBest current price:")
            print(
                f"  {best.supplier}: "
                f"{best.currency} {best.price}"
            )
        else:
            print("\nNo available offers.")


if __name__ == "__main__":
    main()