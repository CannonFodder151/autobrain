/// Native in-app purchase flow via the `in_app_purchase` package.
///
/// Wraps Google Play / App Store billing so the license screen can hand off
/// a purchase with one call.  Server-side verification happens through
/// POST /billing/iap/verify (see backend app.services.iap).
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:in_app_purchase/in_app_purchase.dart';

import '../core/config.dart';
import '../core/auth_state.dart';

/// Thin wrapper around `in_app_purchase` for AutoBrain subscriptions.
class IapService {
  IapService(this._auth);

  final AuthState _auth;
  final _iap = InAppPurchase.instance;
  StreamSubscription<List<PurchaseDetails>>? _sub;

  bool _available = false;
  bool get available => _available;

  /// Product details fetched from the store, keyed by product ID.
  final Map<String, ProductDetails> products = {};

  /// Stream of purchase status updates forwarded to the UI.
  final _purchaseCtl = StreamController<PurchaseDetails>.broadcast();
  Stream<PurchaseDetails> get purchaseStream => _purchaseCtl.stream;

  // ── Lifecycle ──────────────────────────────────────────────────────────

  /// Check store availability and query product details for the given SKUs.
  Future<void> init(List<String> productIds) async {
    if (!AppConfig.isMobile) return;

    _available = await _iap.isAvailable();
    if (!_available) return;

    _sub = _iap.purchaseStream.listen(
      _onPurchaseUpdate,
      onError: (e) => debugPrint('[IAP] purchase stream error: $e'),
    );

    try {
      final resp = await _iap.queryProductDetails(productIds.toSet());
      for (final p in resp.productDetails) {
        products[p.id] = p;
      }
    } catch (e) {
      debugPrint('[IAP] queryProductDetails failed: $e');
    }
  }

  void dispose() {
    _sub?.cancel();
    if (!_purchaseCtl.isClosed) _purchaseCtl.close();
  }

  // ── Purchase ───────────────────────────────────────────────────────────

  /// Kick off a subscription purchase. Returns true if the store dialog was
  /// shown; false on early failure.
  Future<bool> buy(String productId) async {
    if (!_available) return false;
    final details = products[productId];
    if (details == null) {
      debugPrint('[IAP] unknown product: $productId');
      return false;
    }
    return _iap.buyNonConsumable(purchaseParam: PurchaseParam(productDetails: details));
  }

  /// Restore previously purchased subscriptions (e.g. after reinstall).
  Future<void> restorePurchases() async {
    if (!_available) return;
    _iap.restorePurchases();
  }

  // ── Internals ──────────────────────────────────────────────────────────

  void _onPurchaseUpdate(List<PurchaseDetails> purchases) {
    for (final p in purchases) {
      _handlePurchase(p);
    }
  }

  Future<void> _handlePurchase(PurchaseDetails purchase) async {
    if (!_purchaseCtl.isClosed) _purchaseCtl.add(purchase);

    if (purchase.status == PurchaseStatus.purchased ||
        purchase.status == PurchaseStatus.restored) {
      await _verifyOnServer(purchase);
    }

    if (purchase.pendingCompletePurchase) {
      await _iap.completePurchase(purchase);
    }
  }

  Future<bool> _verifyOnServer(PurchaseDetails purchase) async {
    final platform = defaultTargetPlatform == TargetPlatform.iOS ? 'ios' : 'android';
    try {
      final result = await _auth.api.post('/billing/iap/verify', {
        'platform': platform,
        'product_id': purchase.productID,
        'transaction_id': purchase.purchaseID ?? '',
        'purchase_token': purchase.billingClientPurchase.purchaseToken,
        'purchase_time_ms': purchase.transactionDate != null
            ? int.tryParse(purchase.transactionDate!) ?? 0
            : 0,
      }) as Map<String, dynamic>;
      return result['status'] == 'active';
    } catch (e) {
      debugPrint('[IAP] verify failed: $e');
      return false;
    }
  }
}
