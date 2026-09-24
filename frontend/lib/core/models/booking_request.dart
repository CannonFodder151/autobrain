part of models;

class BookingRequestSummary {
  final String id;
  final String engineerId;
  final String? engineerName;
  final double? engineerRating;
  final String? engineerPhone;
  final String vehicleId;
  final String? vehicleMake;
  final String? vehicleModel;
  final String? vehicleRego;
  final String serviceType;
  final String? description;
  final String? preferredDate;
  final String? preferredTime;
  final String urgency;
  final String status;
  final String? createdAt;
  final String? respondedAt;
  final String? engineerNotes;
  final double? quotedPrice;
  final String? scheduledDate;
  final String? scheduledTime;

  const BookingRequestSummary({
    required this.id,
    required this.engineerId,
    this.engineerName,
    this.engineerRating,
    this.engineerPhone,
    required this.vehicleId,
    this.vehicleMake,
    this.vehicleModel,
    this.vehicleRego,
    required this.serviceType,
    this.description,
    this.preferredDate,
    this.preferredTime,
    this.urgency = 'normal',
    this.status = 'pending',
    this.createdAt,
    this.respondedAt,
    this.engineerNotes,
    this.quotedPrice,
    this.scheduledDate,
    this.scheduledTime,
  });

  factory BookingRequestSummary.fromJson(Map<String, dynamic> j) => BookingRequestSummary(
        id: j['id'] as String,
        engineerId: j['engineer_id'] as String,
        engineerName: j['engineer_name'] as String?,
        engineerRating: (j['engineer_rating'] as num?)?.toDouble(),
        engineerPhone: j['engineer_phone'] as String?,
        vehicleId: j['vehicle_id'] as String,
        vehicleMake: j['vehicle_make'] as String?,
        vehicleModel: j['vehicle_model'] as String?,
        vehicleRego: j['vehicle_rego'] as String?,
        serviceType: j['service_type'] as String? ?? 'repair',
        description: j['description'] as String?,
        preferredDate: j['preferred_date'] as String?,
        preferredTime: j['preferred_time'] as String?,
        urgency: (j['urgency'] as String?) ?? 'normal',
        status: (j['status'] as String?) ?? 'pending',
        createdAt: j['created_at'] as String?,
        respondedAt: j['responded_at'] as String?,
        engineerNotes: j['engineer_notes'] as String?,
        quotedPrice: (j['quoted_price'] as num?)?.toDouble(),
        scheduledDate: j['scheduled_date'] as String?,
        scheduledTime: j['scheduled_time'] as String?,
      );

  String get statusLabel {
    switch (status) {
      case 'pending':
        return 'Pending';
      case 'accepted':
        return 'Accepted';
      case 'rejected':
        return 'Rejected';
      case 'completed':
        return 'Completed';
      case 'cancelled':
        return 'Cancelled';
      default:
        return status;
    }
  }

  String get urgencyLabel {
    switch (urgency) {
      case 'low':
        return 'Low';
      case 'normal':
        return 'Normal';
      case 'high':
        return 'High';
      case 'urgent':
        return 'Urgent';
      default:
        return urgency;
    }
  }
}

class BookingRequestDetail {
  final String id;
  final String engineerId;
  final String? engineerName;
  final double? engineerRating;
  final String? engineerPhone;
  final String? engineerEmail;
  final List<String> engineerSpecialties;
  final int? engineerYearsExperience;
  final String vehicleId;
  final String? vehicleMake;
  final String? vehicleModel;
  final String? vehicleRego;
  final int? vehicleYear;
  final String? vehicleNickname;
  final String serviceType;
  final String? description;
  final String? preferredDate;
  final String? preferredTime;
  final String urgency;
  final Map<String, dynamic>? preCheckReport;
  final List<String> symptoms;
  final List<String> mods;
  final int? odometerKm;
  final String status;
  final String? engineerNotes;
  final double? quotedPrice;
  final String? scheduledDate;
  final String? scheduledTime;
  final String? createdAt;
  final String? updatedAt;
  final String? respondedAt;
  final String? completedAt;

  const BookingRequestDetail({
    required this.id,
    required this.engineerId,
    this.engineerName,
    this.engineerRating,
    this.engineerPhone,
    this.engineerEmail,
    this.engineerSpecialties = const [],
    this.engineerYearsExperience,
    required this.vehicleId,
    this.vehicleMake,
    this.vehicleModel,
    this.vehicleRego,
    this.vehicleYear,
    this.vehicleNickname,
    required this.serviceType,
    this.description,
    this.preferredDate,
    this.preferredTime,
    this.urgency = 'normal',
    this.preCheckReport,
    this.symptoms = const [],
    this.mods = const [],
    this.odometerKm,
    this.status = 'pending',
    this.engineerNotes,
    this.quotedPrice,
    this.scheduledDate,
    this.scheduledTime,
    this.createdAt,
    this.updatedAt,
    this.respondedAt,
    this.completedAt,
  });

  factory BookingRequestDetail.fromJson(Map<String, dynamic> j) => BookingRequestDetail(
        id: j['id'] as String,
        engineerId: j['engineer_id'] as String,
        engineerName: j['engineer_name'] as String?,
        engineerRating: (j['engineer_rating'] as num?)?.toDouble(),
        engineerPhone: j['engineer_phone'] as String?,
        engineerEmail: j['engineer_email'] as String?,
        engineerSpecialties: ((j['engineer_specialties'] as List?) ?? [])
            .map((e) => e.toString())
            .toList(),
        engineerYearsExperience: j['engineer_years_experience'] as int?,
        vehicleId: j['vehicle_id'] as String,
        vehicleMake: j['vehicle_make'] as String?,
        vehicleModel: j['vehicle_model'] as String?,
        vehicleRego: j['vehicle_rego'] as String?,
        vehicleYear: j['vehicle_year'] as int?,
        vehicleNickname: j['vehicle_nickname'] as String?,
        serviceType: j['service_type'] as String? ?? 'repair',
        description: j['description'] as String?,
        preferredDate: j['preferred_date'] as String?,
        preferredTime: j['preferred_time'] as String?,
        urgency: (j['urgency'] as String?) ?? 'normal',
        preCheckReport: j['pre_check_report'] as Map<String, dynamic>?,
        symptoms: ((j['symptoms'] as List?) ?? [])
            .map((e) => e.toString())
            .toList(),
        mods: ((j['mods'] as List?) ?? [])
            .map((e) => e.toString())
            .toList(),
        odometerKm: j['odometer_km'] as int?,
        status: (j['status'] as String?) ?? 'pending',
        engineerNotes: j['engineer_notes'] as String?,
        quotedPrice: (j['quoted_price'] as num?)?.toDouble(),
        scheduledDate: j['scheduled_date'] as String?,
        scheduledTime: j['scheduled_time'] as String?,
        createdAt: j['created_at'] as String?,
        updatedAt: j['updated_at'] as String?,
        respondedAt: j['responded_at'] as String?,
        completedAt: j['completed_at'] as String?,
      );
}