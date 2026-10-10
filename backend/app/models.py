from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index, Boolean, Enum as SAEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    
    # Auth
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=False)  # имя для лидерборда
    
    # Intervals.icu привязка (опциональна до первого sync)
    intervals_id = Column(String, unique=True, index=True, nullable=True)
    api_key_encrypted = Column(String(500), nullable=True)  # шифруется Fernet
    
    # Устаревшие поля — оставим для совместимости, но не обязательны
    email = Column(String, unique=True, index=True, nullable=True)
    firstname = Column(String, nullable=True)
    lastname = Column(String, nullable=True)
    profile_picture = Column(String, nullable=True)
    
    # Game data
    total_xp = Column(Float, default=0)
    level = Column(Integer, default=1)
    legacy_xp_offset = Column(Float, default=0.0)            # v6: миграционная компенсация
    xp_migrated_at = Column(DateTime, nullable=True)         # v6: маркер одноразовой миграции
    division_current = Column(Integer, nullable=True)      # PR8: ступень лестницы 1..5
    division_placed_at = Column(DateTime, nullable=True)
    pause_set_at = Column(DateTime, nullable=True)         # PR8: окно паузы
    paused_until = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    activities = relationship("Activity", back_populates="user", cascade="all, delete-orphan")
    wellness_records = relationship("Wellness", back_populates="user", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_users_total_xp', 'total_xp'),
    )


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    intervals_activity_id = Column(String, index=True, nullable=False)

    sleep_multiplier = Column(Float, default=1.0)
    sleep_secs = Column(Integer, nullable=True)
    
    name = Column(String)
    sport_type = Column(String)
    distance = Column(Float)
    moving_time = Column(Integer)
    elapsed_time = Column(Integer, nullable=True)
    elevation_gain = Column(Float)
    
    average_speed = Column(Float, nullable=True)
    max_speed = Column(Float, nullable=True)
    average_heartrate = Column(Float, nullable=True)
    max_heartrate = Column(Float, nullable=True)
    average_watts = Column(Float, nullable=True)
    normalized_power = Column(Float, nullable=True)
    
    training_load = Column(Float, nullable=True)
    intensity = Column(Float, nullable=True)
    
    xp_earned = Column(Float, default=0)
    base_xp = Column(Float, default=0)
    intensity_multiplier = Column(Float, default=1.0)
    intensity_category = Column(String, nullable=True)      # LOW | MEDIUM | HIGH
    intensity_reason = Column(String, nullable=True)        # текст для Activity Card
    streak_multiplier = Column(Float, default=1.0)          # множитель дневного streak
    streak_reason = Column(String, nullable=True)           # текст для Activity Card
    rate_per_hour = Column(Float, default=0.0)               # ставка XP/ч (для разбивки)
    tss = Column(Float, nullable=True)                       # v6: нагрузка (реал/оценка)
    tss_estimated = Column(Boolean, default=False)           # v6: нагрузка оценочная
    is_long = Column(Boolean, default=False)                 # v6: ≥1.3× своей медианы      
    is_manual = Column(Boolean, default=False)             # PR8: ручная запись       
    
    start_date = Column(DateTime)
    start_date_local = Column(DateTime, nullable=True)
    
    indoor = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="activities")
    
    __table_args__ = (
        Index('idx_activities_user_date', 'user_id', 'start_date'),
        Index('idx_activities_intervals_id', 'user_id', 'intervals_activity_id', unique=True),
    )


class Wellness(Base):
    __tablename__ = "wellness"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(String, nullable=False, index=True)

    sleep_secs = Column(Integer, nullable=True)
    sleep_score = Column(Float, nullable=True)
    sleep_quality = Column(Integer, nullable=True)
    avg_sleeping_hr = Column(Float, nullable=True)
    resting_hr = Column(Integer, nullable=True)
    hrv = Column(Float, nullable=True)
    fatigue = Column(Integer, nullable=True)
    soreness = Column(Integer, nullable=True)
    stress = Column(Integer, nullable=True)
    mood = Column(Integer, nullable=True)
    readiness = Column(Float, nullable=True)
    weight = Column(Float, nullable=True)
    ctl = Column(Float, nullable=True)
    atl = Column(Float, nullable=True)
    sleep_xp = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="wellness_records")

    __table_args__ = (
        Index("idx_wellness_user_date", "user_id", "date", unique=True),
    )


class FriendshipStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"


class Friendship(Base):
    __tablename__ = "friendships"
    
    id = Column(Integer, primary_key=True, index=True)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(SAEnum(FriendshipStatus), default=FriendshipStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])
    
    __table_args__ = (
        Index("idx_friendship_unique", "from_user_id", "to_user_id", unique=True),
        Index("idx_friendship_status", "status"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String, nullable=False)      # friend_request | friend_accepted | system
    text = Column(String, nullable=False)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="notifications")



class WeeklySummary(Base):
    __tablename__ = "weekly_summaries"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    week_start = Column(DateTime, nullable=False)          # понедельник 00:00
    actual_load = Column(Float, default=0)
    target_load = Column(Float, nullable=True)
    completion_ratio = Column(Float, nullable=True)
    training_days = Column(Integer, default=0)
    target_training_days = Column(Integer, nullable=True)
    effort_xp = Column(Float, default=0)
    goal_xp = Column(Float, default=0)
    consistency_xp = Column(Float, default=0)
    quality_xp = Column(Float, default=0)
    recovery_xp = Column(Float, default=0)
    quest_xp = Column(Float, default=0)
    total_xp = Column(Float, default=0)
    league_score = Column(Float, nullable=True)
    division = Column(String, nullable=True)
    division_source = Column(String, nullable=True)        # ctl | load_fallback | provisional
    finalized = Column(Boolean, default=False)
    is_deload = Column(Boolean, default=False)             # PR8: разгрузочная неделя
    paused = Column(Boolean, default=False)                # PR8: неделя паузы
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("uq_weekly_summary_user_week", "user_id", "week_start", unique=True),
    )


class XPEvent(Base):
    __tablename__ = "xp_events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    week_start = Column(DateTime, nullable=False)
    date = Column(DateTime, nullable=False)
    event_type = Column(String, nullable=False)   # consistency|quality_hard|quality_long|weekly_goal|recovery|quest|achievement
    event_key = Column(String, nullable=False)    # стабильный ключ идемпотентности
    amount = Column(Float, nullable=False, default=0)
    source_type = Column(String, nullable=True)   # day | week | quest
    source_id = Column(String, nullable=True)
    title = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("uq_xp_event_key", "user_id", "event_key", unique=True),
        Index("ix_xp_events_user_week", "user_id", "week_start"),
    )


class LeagueWeek(Base):
    __tablename__ = "league_weeks"

    id = Column(Integer, primary_key=True)
    week_start = Column(DateTime, nullable=False, unique=True)
    status = Column(String, default="closed")   # closed | not_formed
    created_at = Column(DateTime, default=datetime.utcnow)


class LeagueMembership(Base):
    __tablename__ = "league_memberships"

    id = Column(Integer, primary_key=True)
    week_start = Column(DateTime, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    division = Column(String, nullable=True)         # имя дивизиона или None (provisional)
    division_source = Column(String, nullable=True)  # ctl | load_fallback | provisional
    league_score = Column(Float, default=0)
    rank = Column(Integer, nullable=True)            # ранг внутри своей лиги
    group_key = Column(String, nullable=True)        # лейбл слившейся группы
    promoted = Column(Boolean, default=False)
    demoted = Column(Boolean, default=False)
    protected = Column(Boolean, default=False)       # защита новичка
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("uq_league_membership", "week_start", "user_id", unique=True),
    )