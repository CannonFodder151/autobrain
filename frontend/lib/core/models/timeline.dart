part of models;

class TimelineEvent {
  final String id, eventType, title;
  final String occurredOn;
  final int? odometerKm;
  final double? amount;

  const TimelineEvent({
    required this.id,
    required this.eventType,
    required this.title,
    required this.occurredOn,
    this.odometerKm,
    this.amount,
  });

  factory TimelineEvent.fromJson(Map<String, dynamic> j) => TimelineEvent(
        id: j['id'] as String,
        eventType: j['event_type'] as String,
        title: j['title'] as String,
        occurredOn: j['occurred_on'] as String,
        odometerKm: j['odometer_km'] as int?,
        amount: (j['amount'] as num?)?.toDouble(),
      );
}
