from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable: referenced artists are first known only by their URL slug.
    genius_id: Mapped[int | None] = mapped_column(unique=True)
    name: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(500), unique=True)

    songs: Mapped[list["Song"]] = relationship(back_populates="primary_artist")


class Song(Base):
    __tablename__ = "songs"

    id: Mapped[int] = mapped_column(primary_key=True)
    genius_id: Mapped[int] = mapped_column(unique=True)
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(500))
    primary_artist_id: Mapped[int] = mapped_column(ForeignKey("artists.id"))

    primary_artist: Mapped[Artist] = relationship(back_populates="songs")
    references: Mapped[list["Reference"]] = relationship(back_populates="song")


class Reference(Base):
    __tablename__ = "references"
    __table_args__ = (UniqueConstraint(
        "song_id", "referenced_artist_id", "annotation_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id"))
    referenced_artist_id: Mapped[int] = mapped_column(ForeignKey("artists.id"))
    annotation_id: Mapped[int]
    fragment: Mapped[str] = mapped_column(Text)

    song: Mapped[Song] = relationship(back_populates="references")
    referenced_artist: Mapped[Artist] = relationship()
