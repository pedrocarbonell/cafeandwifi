"""Cafe catalogue: owns the Cafe data and every rule about it.

Callers go through `Catalogue`; nothing else touches the database.
"""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Engine,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    inspect,
    text,
    func,
    insert,
    select,
    update,
)

from .attributes import SEATING_BANDS, pence_from_pounds, seating_band
from .filters import Filters

metadata = MetaData()

cafe_table = Table(
    "cafe",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(250), nullable=False, unique=True),
    Column("neighbourhood", String(250), nullable=False),
    Column("latitude", Float),
    Column("longitude", Float),
    # Not unique: several Cafes may share a Google place (ADR-0001).
    Column("google_place_id", String(250)),
    Column("has_wifi", Boolean, nullable=False),
    Column("has_sockets", Boolean, nullable=False),
    Column("has_toilet", Boolean, nullable=False),
    Column("calls_permitted", Boolean, nullable=False),
    Column(
        "seating_capacity",
        String(10),
        CheckConstraint(
            "seating_capacity IN ({})".format(
                ", ".join(f"'{band}'" for band in SEATING_BANDS)
            )
        ),
        nullable=False,
    ),
    Column(
        "coffee_price_pence",
        Integer,
        CheckConstraint("coffee_price_pence >= 0"),
        nullable=False,
    ),
    # Carried over from the original data until every Cafe has a Place ID.
    Column("map_url", String(500)),
    Column("img_url", String(500)),
)


@dataclass(frozen=True)
class CafeDetails:
    """Everything the Curator records about a Cafe."""

    name: str
    neighbourhood: str
    latitude: float | None
    longitude: float | None
    google_place_id: str | None
    has_wifi: bool
    has_sockets: bool
    has_toilet: bool
    calls_permitted: bool
    seating_capacity: str
    coffee_price_pence: int


@dataclass(frozen=True)
class Cafe(CafeDetails):
    id: int

    @property
    def positioned(self) -> bool:
        return self.latitude is not None and self.longitude is not None


class InvalidCafe(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


class DuplicateName(InvalidCafe):
    def __init__(self, name: str):
        super().__init__("name", f"There is already a Cafe called “{name}”.")


DETAIL_COLUMNS = [
    cafe_table.c[name] for name in CafeDetails.__dataclass_fields__
]


class Catalogue:
    def __init__(self, engine: Engine):
        self._engine = engine

    @classmethod
    def at(cls, database_path: str) -> "Catalogue":
        engine = create_engine(f"sqlite:///{database_path}")
        metadata.create_all(engine)
        return cls(engine)

    def find(self, filters: Filters) -> list[Cafe]:
        """Positioned Cafes satisfying every Filter, by name."""
        c = cafe_table.c
        query = self._select().where(c.latitude.is_not(None), c.longitude.is_not(None))
        if filters.wifi:
            query = query.where(c.has_wifi.is_(True))
        if filters.sockets:
            query = query.where(c.has_sockets.is_(True))
        if filters.toilet:
            query = query.where(c.has_toilet.is_(True))
        if filters.calls:
            query = query.where(c.calls_permitted.is_(True))
        if filters.min_seating is not None:
            smallest = SEATING_BANDS.index(filters.min_seating)
            query = query.where(c.seating_capacity.in_(SEATING_BANDS[smallest:]))
        if filters.max_price_pence is not None:
            query = query.where(c.coffee_price_pence <= filters.max_price_pence)
        return self._fetch(query)

    def all(self) -> list[Cafe]:
        """Every Cafe, positioned or not, by name."""
        return self._fetch(self._select())

    def get(self, cafe_id: int) -> Cafe | None:
        found = self._fetch(self._select().where(cafe_table.c.id == cafe_id))
        return found[0] if found else None

    def sharing_place(self, place_id: str, except_id: int | None = None) -> list[Cafe]:
        """Other Cafes already matched to this Google place."""
        query = self._select().where(cafe_table.c.google_place_id == place_id)
        if except_id is not None:
            query = query.where(cafe_table.c.id != except_id)
        return self._fetch(query)

    def neighbourhoods(self) -> list[str]:
        query = (
            select(cafe_table.c.neighbourhood)
            .distinct()
            .order_by(cafe_table.c.neighbourhood)
        )
        with self._engine.connect() as conn:
            return list(conn.scalars(query))

    def add(self, details: CafeDetails) -> Cafe:
        details = self._checked(details)
        with self._engine.begin() as conn:
            self._ensure_name_free(conn, details.name)
            cafe_id = conn.execute(
                insert(cafe_table).values(**vars(details)).returning(cafe_table.c.id)
            ).scalar_one()
        return Cafe(**vars(details), id=cafe_id)

    def update(self, cafe_id: int, details: CafeDetails) -> Cafe | None:
        details = self._checked(details)
        with self._engine.begin() as conn:
            self._ensure_name_free(conn, details.name, except_id=cafe_id)
            changed = conn.execute(
                update(cafe_table)
                .where(cafe_table.c.id == cafe_id)
                .values(**vars(details))
            ).rowcount
        return Cafe(**vars(details), id=cafe_id) if changed else None

    def delete(self, cafe_id: int) -> bool:
        with self._engine.begin() as conn:
            return bool(
                conn.execute(delete(cafe_table).where(cafe_table.c.id == cafe_id)).rowcount
            )

    def _select(self):
        return select(cafe_table.c.id, *DETAIL_COLUMNS).order_by(
            func.lower(cafe_table.c.name)
        )

    def _fetch(self, query) -> list[Cafe]:
        with self._engine.connect() as conn:
            return [Cafe(**row._asdict()) for row in conn.execute(query)]

    @staticmethod
    def _ensure_name_free(conn, name: str, except_id: int | None = None) -> None:
        query = select(cafe_table.c.id).where(func.lower(cafe_table.c.name) == name.lower())
        if except_id is not None:
            query = query.where(cafe_table.c.id != except_id)
        if conn.execute(query).first():
            raise DuplicateName(name)

    @staticmethod
    def _checked(details: CafeDetails) -> CafeDetails:
        name = details.name.strip()
        neighbourhood = details.neighbourhood.strip()
        place_id = (details.google_place_id or "").strip() or None
        if not name:
            raise InvalidCafe("name", "Give the Cafe a name.")
        if not neighbourhood:
            raise InvalidCafe("neighbourhood", "Choose a Neighbourhood for the Cafe.")
        if details.seating_capacity not in SEATING_BANDS:
            raise InvalidCafe("seating_capacity", "Choose a Seating capacity band.")
        if details.coffee_price_pence < 0:
            raise InvalidCafe("coffee_price", "Coffee price can't be negative.")
        if (details.latitude is None) != (details.longitude is None):
            raise InvalidCafe("position", "A Position needs both latitude and longitude.")
        if details.latitude is not None and details.longitude is not None:
            if not (-90 <= details.latitude <= 90 and -180 <= details.longitude <= 180):
                raise InvalidCafe("position", "That Position is not on Earth.")
        return CafeDetails(
            **{
                **vars(details),
                "name": name,
                "neighbourhood": neighbourhood,
                "google_place_id": place_id,
            }
        )


class AlreadyImported(Exception):
    pass


class UnrecognisedOriginalData(ValueError):
    pass


@dataclass(frozen=True)
class ImportReport:
    imported: int
    positioned: int


Position = tuple[float, float]


def import_original_cafes(
    catalogue: Catalogue, position_from_link: Callable[[str], Position | None]
) -> ImportReport:
    """Normalise the original `cafe` table in place, once.

    Renames `location` to Neighbourhood, `can_take_calls` to Calls policy,
    free-text seats to Seating capacity bands and "£2.40" prices to pence, and
    gives a Position to Cafes whose map link carries coordinates. Every row is
    checked before anything is changed.
    """
    engine = catalogue._engine
    columns = {column["name"] for column in inspect(engine).get_columns("cafe")}
    if "location" not in columns:
        raise AlreadyImported("The original Cafes have already been imported.")

    with engine.connect() as conn:
        originals = conn.execute(text("SELECT * FROM cafe ORDER BY id")).mappings().all()

    problems = []
    for row in originals:
        if seating_band(row["seats"] or "") is None:
            problems.append(f"{row['name']}: seats “{row['seats']}” is not a Seating capacity band")
        if pence_from_pounds(row["coffee_price"] or "") is None:
            problems.append(f"{row['name']}: coffee price “{row['coffee_price']}” is not in pounds")
    if problems:
        raise UnrecognisedOriginalData("\n".join(problems))

    rows = []
    for row in originals:
        position = position_from_link(row["map_url"])
        rows.append(
            {
                "id": row["id"],
                "name": row["name"],
                "neighbourhood": row["location"],
                "latitude": position[0] if position else None,
                "longitude": position[1] if position else None,
                "google_place_id": None,
                "has_wifi": bool(row["has_wifi"]),
                "has_sockets": bool(row["has_sockets"]),
                "has_toilet": bool(row["has_toilet"]),
                "calls_permitted": bool(row["can_take_calls"]),
                "seating_capacity": seating_band(row["seats"]),
                "coffee_price_pence": pence_from_pounds(row["coffee_price"]),
                "map_url": row["map_url"],
                "img_url": row["img_url"],
            }
        )

    replacement = cafe_table.to_metadata(MetaData(), name="cafe_imported")
    with engine.begin() as conn:
        replacement.create(conn)
        if rows:
            conn.execute(insert(replacement), rows)
        conn.execute(text("DROP TABLE cafe"))
        conn.execute(text("ALTER TABLE cafe_imported RENAME TO cafe"))

    return ImportReport(
        imported=len(rows), positioned=sum(row["latitude"] is not None for row in rows)
    )
