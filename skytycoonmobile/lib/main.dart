// SkyTycoon Mobile App Engine - Multilingual DE/EN
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'dart:io';
import 'package:shared_preferences/shared_preferences.dart';

class MyHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) {
    return super.createHttpClient(context)
      ..badCertificateCallback =
          (X509Certificate cert, String host, int port) => true;
  }
}

void main() {
  HttpOverrides.global = MyHttpOverrides();
  runApp(const SkyTycoonMobileApp());
}

class MobileLocalization {
  static const Map<String, Map<String, String>> _localizedValues = {
    'de': {
      'app.title': '👨‍✈️ SKYTYCOON MOBILE',
      'app.subtitle': 'FLUGBETRIEBS- & MANAGERZENTRALE',
      'login.btn': 'IN DIE CLOUD EINLOGGEN',
      'login.error': 'Login fehlgeschlagen: Passwort oder Name inkorrekt.',
      'login.net_error': 'Verbindung zum IONOS XXL Server fehlgeschlagen:',
      'nav.fids': 'Live-Flugtafel',
      'nav.jobs': 'Job-Börse',
      'nav.account': 'Kundenkonto',
      'nav.alliance': 'Allianz',
      'fids.title': '📡 OPERATIONS-ZENTRALE',
      'fids.route': 'Route',
      'fids.loading': 'Lade weltweite Flugbewegungen direkt vom IONOS-Server...',
      'fids.empty': 'Aktuell befinden sich alle Maschinen am Boden.',
      'jobs.title': '📋 Job-Börse',
      'jobs.loading': 'Lade offene Job-Angebote...',
      'jobs.empty': 'Keine aktuellen Job-Angebote verfügbar.',
      'jobs.accept': 'Annehmen',
      'jobs.accepted': 'Job angenommen',
      'jobs.failed': 'Job konnte nicht angenommen werden.',
      'account.title': '👤 Kundenkonto',
      'account.loading': 'Lade Kontodaten...',
      'account.offline': 'Offline-Modus: Verwende zwischengespeicherte Daten.',
      'account.credits': 'Credits',
      'account.xp': 'XP',
      'account.rep': 'Reputation',
      'account.loan': 'Kredit',
      'account.tax': 'Bonität',
      'account.alliance': 'Allianzstatus',
      'account.no_alliance': 'Du bist derzeit in keiner Allianz.',
      'account.create_btn': 'Allianz gründen',
      'account.join_btn': 'Beitreten',
      'alliance.title': '🤝 Allianz-Center',
      'alliance.role': 'Rolle',
      'alliance.pool': 'Allianz-Konto',
      'alliance.tax': 'Steuer',
      'alliance.leases': 'Streckenvermietungen',
      'alliance.pending': 'Beitrittsanfrage gesendet',
      'refresh': 'Aktualisieren',
      'logout': 'Abmelden',
    },
    'en': {
      'app.title': '👨‍✈️ SKYTYCOON MOBILE',
      'app.subtitle': 'FLIGHT OPERATIONS & MANAGER HUB',
      'login.btn': 'LOGIN TO CLOUD NETWORK',
      'login.error': 'Login failed: Invalid credentials provided.',
      'login.net_error': 'Connection to IONOS XXL server failed:',
      'nav.fids': 'Live Board',
      'nav.jobs': 'Job Board',
      'nav.account': 'Account',
      'nav.alliance': 'Alliance',
      'fids.title': '📡 TACTICAL OPERATIONS',
      'fids.route': 'Route',
      'fids.loading': 'Loading live flight traffic from IONOS server...',
      'fids.empty': 'All aircraft are currently parked on the ground.',
      'jobs.title': '📋 Job Board',
      'jobs.loading': 'Loading available jobs...',
      'jobs.empty': 'No current job offers available.',
      'jobs.accept': 'Accept',
      'jobs.accepted': 'Job accepted',
      'jobs.failed': 'Unable to claim the job.',
      'account.title': '👤 Account',
      'account.loading': 'Loading account data...',
      'account.offline': 'Offline mode: using cached data.',
      'account.credits': 'Credits',
      'account.xp': 'XP',
      'account.rep': 'Reputation',
      'account.loan': 'Loan',
      'account.tax': 'Credit score',
      'account.alliance': 'Alliance status',
      'account.no_alliance': 'You are not part of an alliance.',
      'account.create_btn': 'Create alliance',
      'account.join_btn': 'Join',
      'alliance.title': '🤝 Alliance Center',
      'alliance.role': 'Role',
      'alliance.pool': 'Alliance treasury',
      'alliance.tax': 'Tax',
      'alliance.leases': 'Route leases',
      'alliance.pending': 'Application sent',
      'refresh': 'Refresh',
      'logout': 'Logout',
    },
  };

  static String tr(String key, String lang) {
    return _localizedValues[lang]?[key] ?? key;
  }
}

const String _serverBaseUrl = 'https://skytycoon.info';
const String _mobileLoginUrl = '$_serverBaseUrl/api/v1/auth/mobile_login';
const String _mobileAccountUrl = '$_serverBaseUrl/api/v1/mobile/account';
const String _radarUrl = '$_serverBaseUrl/api/v1/web/radar/positions';
const String _jobsUrl = '$_serverBaseUrl/api/v1/jobs/available?icao=ALL';
const String _jobAcceptUrl = '$_serverBaseUrl/api/v1/jobs/accept';
const String _allianceCreateUrl = '$_serverBaseUrl/api/v1/user/alliance/create';
const String _allianceJoinUrl = '$_serverBaseUrl/api/v1/user/alliance/join';

Future<SharedPreferences> _sharedPrefs() async {
  return SharedPreferences.getInstance();
}

Future<void> _saveCache(String key, dynamic value) async {
  try {
    final prefs = await _sharedPrefs();
    await prefs.setString(key, jsonEncode(value));
  } catch (_) {}
}

Future<Map<String, dynamic>?> _loadJsonCache(String key) async {
  try {
    final prefs = await _sharedPrefs();
    final raw = prefs.getString(key);
    if (raw == null) return null;
    final parsed = jsonDecode(raw);
    if (parsed is Map<String, dynamic>) return parsed;
  } catch (_) {}
  return null;
}

Future<List<dynamic>?> _loadListCache(String key) async {
  try {
    final prefs = await _sharedPrefs();
    final raw = prefs.getString(key);
    if (raw == null) return null;
    final parsed = jsonDecode(raw);
    if (parsed is List<dynamic>) return parsed;
  } catch (_) {}
  return null;
}

Future<void> _saveAuthData(String token, String pilotName, String email) async {
  final prefs = await _sharedPrefs();
  await prefs.setString('mobile_token', token);
  await prefs.setString('mobile_pilot_name', pilotName);
  await prefs.setString('mobile_email', email);
}

Future<void> _clearAuthData() async {
  final prefs = await _sharedPrefs();
  await prefs.remove('mobile_token');
  await prefs.remove('mobile_pilot_name');
  await prefs.remove('mobile_email');
}

Future<String?> _getSavedToken() async {
  final prefs = await _sharedPrefs();
  return prefs.getString('mobile_token');
}

Future<String?> _getSavedPilotName() async {
  final prefs = await _sharedPrefs();
  return prefs.getString('mobile_pilot_name');
}

Future<String?> _getSavedEmail() async {
  final prefs = await _sharedPrefs();
  return prefs.getString('mobile_email');
}

Future<Map<String, dynamic>> _apiLogin(String login, String password) async {
  final body = <String, dynamic>{
    'password': password,
    'portal_email': login,
    'pilot_name': login,
    'username': login,
  };
  final response = await http
      .post(Uri.parse(_mobileLoginUrl), headers: {'Content-Type': 'application/json'}, body: jsonEncode(body))
      .timeout(const Duration(seconds: 12));
  final data = jsonDecode(response.body);
  if (response.statusCode == 200 && data is Map && data['status'] == 'success') {
    return Map<String, dynamic>.from(data as Map);
  }
  throw Exception(data is Map ? (data['status'] ?? data['error'] ?? 'login_failed') : 'login_failed');
}

Future<Map<String, dynamic>> _apiAccount(String token) async {
  final response = await http.post(
    Uri.parse(_mobileAccountUrl),
    headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $token'},
    body: jsonEncode(<String, dynamic>{}),
  ).timeout(const Duration(seconds: 12));
  final data = jsonDecode(response.body);
  if (response.statusCode == 200 && data is Map && data['ok'] == true) {
    return Map<String, dynamic>.from(data as Map);
  }
  throw Exception(data is Map ? (data['error'] ?? 'account_failed') : 'account_failed');
}

Future<List<dynamic>> _apiRadarPositions() async {
  final response = await http.get(Uri.parse(_radarUrl)).timeout(const Duration(seconds: 12));
  final data = jsonDecode(response.body);
  return (data is Map ? (data['pilots'] as List<dynamic>?) : null) ?? [];
}

Future<List<dynamic>> _apiJobBoard() async {
  final response = await http.get(Uri.parse(_jobsUrl)).timeout(const Duration(seconds: 12));
  final data = jsonDecode(response.body);
  return (data is Map ? (data['jobs'] as List<dynamic>?) : null) ?? [];
}

Future<bool> _apiAcceptJob(String token, int jobId) async {
  final response = await http
      .post(Uri.parse(_jobAcceptUrl),
          headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $token'},
          body: jsonEncode({'job_id': jobId}))
      .timeout(const Duration(seconds: 12));
  final data = jsonDecode(response.body);
  return response.statusCode == 200 && data is Map && data['ok'] == true;
}

Future<Map<String, dynamic>> _apiCreateAlliance(String token, String name) async {
  final response = await http
      .post(Uri.parse(_allianceCreateUrl),
          headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $token'},
          body: jsonEncode({'name': name}))
      .timeout(const Duration(seconds: 12));
  final data = jsonDecode(response.body);
  return data is Map ? Map<String, dynamic>.from(data) : {'ok': false, 'error': 'invalid_response'};
}

Future<Map<String, dynamic>> _apiJoinAlliance(String token, String allianceId) async {
  final response = await http
      .post(Uri.parse(_allianceJoinUrl),
          headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $token'},
          body: jsonEncode({'alliance_id': allianceId}))
      .timeout(const Duration(seconds: 12));
  final data = jsonDecode(response.body);
  return data is Map ? Map<String, dynamic>.from(data) : {'ok': false, 'error': 'invalid_response'};
}

class SkyTycoonMobileApp extends StatelessWidget {
  const SkyTycoonMobileApp({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    String systemLocale = Platform.localeName.split('_').first;
    if (systemLocale != 'de') systemLocale = 'en';

    return MaterialApp(
      title: 'SkyTycoon Pro Mobile',
      locale: Locale(systemLocale),
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF05070a),
        primaryColor: const Color(0xFF0088ff),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFFd4af37),
          secondary: Color(0xFF00ff66),
        ),
      ),
      home: MobileLoginScreen(currentLang: systemLocale),
    );
  }
}

class MobileLoginScreen extends StatefulWidget {
  final String currentLang;
  const MobileLoginScreen({Key? key, required this.currentLang}) : super(key: key);

  @override
  State<MobileLoginScreen> createState() => _MobileLoginScreenState();
}

class _MobileLoginScreenState extends State<MobileLoginScreen> {
  final TextEditingController _loginController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    _checkSavedSession();
  }

  Future<void> _checkSavedSession() async {
    final token = await _getSavedToken();
    if (token != null && token.isNotEmpty) {
      _navigateToDashboard();
    }
  }

  Future<void> _executeLogin() async {
    if (_loginController.text.trim().isEmpty || _passwordController.text.trim().isEmpty) {
      _showErrorDialog(MobileLocalization.tr('login.error', widget.currentLang));
      return;
    }
    setState(() => _isLoading = true);
    try {
      final result = await _apiLogin(_loginController.text.trim(), _passwordController.text.trim());
      final token = result['token'] as String? ?? '';
      final pilotName = result['pilot_name'] as String? ?? _loginController.text.trim();
      final email = result['email'] as String? ?? '';
      if (token.isEmpty) throw Exception('login_failed');
      await _saveAuthData(token, pilotName, email);
      await _refreshCachedData(token);
      _navigateToDashboard();
    } catch (e) {
      _showErrorDialog('${MobileLocalization.tr('login.net_error', widget.currentLang)} ${e.toString()}');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _refreshCachedData(String token) async {
    try {
      final account = await _apiAccount(token);
      await _saveCache('cache_account', account);
    } catch (_) {}
    try {
      final radar = await _apiRadarPositions();
      await _saveCache('cache_fids', radar);
    } catch (_) {}
    try {
      final jobs = await _apiJobBoard();
      await _saveCache('cache_jobs', jobs);
    } catch (_) {}
  }

  void _navigateToDashboard() {
    if (!mounted) return;
    Navigator.pushReplacement(
      context,
      MaterialPageRoute(builder: (context) => MobileOperationsHub(currentLang: widget.currentLang)),
    );
  }

  void _showErrorDialog(String msg) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF111520),
        title: const Text('⚠️ Login', style: TextStyle(color: Color(0xFFff3333), fontFamily: 'monospace')),
        content: Text(msg, style: const TextStyle(color: Colors.white)),
        actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('OK'))],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Center(
          child: SingleChildScrollView(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(MobileLocalization.tr('app.title', widget.currentLang), textAlign: TextAlign.center, style: const TextStyle(fontSize: 26, fontWeight: FontWeight.bold, color: Color(0xFFd4af37))),
                const SizedBox(height: 8),
                Text(MobileLocalization.tr('app.subtitle', widget.currentLang), textAlign: TextAlign.center, style: const TextStyle(fontSize: 12, color: Colors.grey, letterSpacing: 1)),
                const SizedBox(height: 30),
                TextField(controller: _loginController, decoration: InputDecoration(labelText: widget.currentLang == 'de' ? 'E-Mail / Pilotname / Lizenz' : 'Email / Pilot Name / License', border: const OutlineInputBorder())),
                const SizedBox(height: 16),
                TextField(controller: _passwordController, obscureText: true, decoration: InputDecoration(labelText: widget.currentLang == 'de' ? 'Passwort' : 'Password', border: const OutlineInputBorder())),
                const SizedBox(height: 24),
                _isLoading
                    ? const Center(child: CircularProgressIndicator())
                    : ElevatedButton(
                        onPressed: _executeLogin,
                        style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFFd4af37), foregroundColor: Colors.black, padding: const EdgeInsets.symmetric(vertical: 14)),
                        child: Text(MobileLocalization.tr('login.btn', widget.currentLang), style: const TextStyle(fontWeight: FontWeight.bold)),
                      ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class MobileOperationsHub extends StatefulWidget {
  final String currentLang;
  const MobileOperationsHub({Key? key, required this.currentLang}) : super(key: key);

  @override
  State<MobileOperationsHub> createState() => _MobileOperationsHubState();
}

class _MobileOperationsHubState extends State<MobileOperationsHub> {
  int _currentIndex = 0;
  String _token = '';
  String _pilotName = '';
  String _email = '';
  Map<String, dynamic>? _accountData;
  List<dynamic> _jobs = [];
  List<dynamic> _fids = [];
  bool _loading = true;
  bool _offlineMode = false;
  String _statusMessage = '';

  @override
  void initState() {
    super.initState();
    _initializeDashboard();
  }

  Future<void> _initializeDashboard() async {
    final token = await _getSavedToken();
    final pilot = await _getSavedPilotName();
    final email = await _getSavedEmail();
    if (token == null || pilot == null) {
      _logout();
      return;
    }
    setState(() {
      _token = token;
      _pilotName = pilot;
      _email = email ?? '';
    });
    await _loadAllData();
  }

  Future<void> _loadAllData() async {
    setState(() {
      _loading = true;
      _offlineMode = false;
      _statusMessage = '';
    });
    try {
      final profile = await _apiAccount(_token);
      final radar = await _apiRadarPositions();
      final jobs = await _apiJobBoard();
      setState(() {
        _accountData = profile;
        _fids = radar;
        _jobs = jobs;
      });
      await _saveCache('cache_account', _accountData ?? {});
      await _saveCache('cache_fids', _fids);
      await _saveCache('cache_jobs', _jobs);
    } catch (error) {
      final savedAccount = await _loadJsonCache('cache_account');
      final savedFids = await _loadListCache('cache_fids');
      final savedJobs = await _loadListCache('cache_jobs');
      if (savedAccount != null || savedFids != null || savedJobs != null) {
        setState(() {
          _offlineMode = true;
          _accountData = savedAccount;
          _fids = savedFids ?? [];
          _jobs = savedJobs ?? [];
          _statusMessage = MobileLocalization.tr('account.offline', widget.currentLang);
        });
      } else {
        setState(() {
          _statusMessage = error.toString();
        });
      }
    } finally {
      setState(() => _loading = false);
    }
  }

  void _logout() async {
    await _clearAuthData();
    if (!mounted) return;
    Navigator.pushReplacement(context, MaterialPageRoute(builder: (context) => MobileLoginScreen(currentLang: widget.currentLang)));
  }

  Future<void> _acceptJob(int jobId) async {
    if (_token.isEmpty) return;
    final ok = await _apiAcceptJob(_token, jobId);
    if (ok) {
      setState(() {
        _jobs.removeWhere((j) => int.tryParse('${j['job_id'] ?? j['id'] ?? 0}') == jobId);
      });
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(MobileLocalization.tr('jobs.accepted', widget.currentLang))));
    } else {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(MobileLocalization.tr('jobs.failed', widget.currentLang))));
    }
  }

  Future<void> _createAlliance(String name) async {
    if (_token.isEmpty) return;
    final result = await _apiCreateAlliance(_token, name);
    if (result['ok'] == true) {
      await _loadAllData();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Alliance created')));
    } else {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(result['error']?.toString() ?? 'Failed')));
    }
  }

  Future<void> _joinAlliance(String allianceId) async {
    if (_token.isEmpty) return;
    final result = await _apiJoinAlliance(_token, allianceId);
    if (result['ok'] == true) {
      await _loadAllData();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(MobileLocalization.tr('alliance.pending', widget.currentLang))));
    } else {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(result['error']?.toString() ?? 'Failed')));
    }
  }

  Widget _currentTab() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    switch (_currentIndex) {
      case 0:
        return MobileFidsTab(lang: widget.currentLang, positions: _fids, statusMessage: _statusMessage);
      case 1:
        return MobileJobsTab(lang: widget.currentLang, jobs: _jobs, onAccept: _acceptJob);
      case 2:
        return MobileAccountTab(lang: widget.currentLang, accountData: _accountData, statusMessage: _statusMessage, onRefresh: _loadAllData);
      case 3:
        return MobileAllianceTab(lang: widget.currentLang, accountData: _accountData, createAlliance: _createAlliance, joinAlliance: _joinAlliance);
      default:
        return const SizedBox.shrink();
    }
  }

  @override
  Widget build(BuildContext context) {
    final title = [
      MobileLocalization.tr('fids.title', widget.currentLang),
      MobileLocalization.tr('jobs.title', widget.currentLang),
      MobileLocalization.tr('account.title', widget.currentLang),
      MobileLocalization.tr('alliance.title', widget.currentLang),
    ][_currentIndex];

    return Scaffold(
      appBar: AppBar(
        title: Text('$title • ${_pilotName.isNotEmpty ? _pilotName : 'SkyTycoon'}', style: const TextStyle(fontFamily: 'monospace', fontWeight: FontWeight.bold, color: Color(0xFFd4af37))),
        backgroundColor: const Color(0xFF12161f),
        centerTitle: true,
        actions: [
          IconButton(icon: const Icon(Icons.refresh, color: Colors.white), onPressed: _loadAllData),
          IconButton(icon: const Icon(Icons.power_settings_new, color: Colors.redAccent), onPressed: _logout),
        ],
      ),
      body: _currentTab(),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        backgroundColor: const Color(0xFF12161f),
        selectedItemColor: const Color(0xFFd4af37),
        unselectedItemColor: Colors.grey,
        onTap: (index) => setState(() => _currentIndex = index),
        items: [
          BottomNavigationBarItem(icon: const Icon(Icons.flight_takeoff), label: MobileLocalization.tr('nav.fids', widget.currentLang)),
          BottomNavigationBarItem(icon: const Icon(Icons.format_list_bulleted), label: MobileLocalization.tr('nav.jobs', widget.currentLang)),
          BottomNavigationBarItem(icon: const Icon(Icons.account_circle), label: MobileLocalization.tr('nav.account', widget.currentLang)),
          BottomNavigationBarItem(icon: const Icon(Icons.handshake), label: MobileLocalization.tr('nav.alliance', widget.currentLang)),
        ],
      ),
    );
  }
}

class MobileFidsTab extends StatelessWidget {
  final String lang;
  final List<dynamic> positions;
  final String statusMessage;
  const MobileFidsTab({Key? key, required this.lang, required this.positions, required this.statusMessage}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    if (positions.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Text(statusMessage.isNotEmpty ? statusMessage : MobileLocalization.tr('fids.empty', lang), textAlign: TextAlign.center, style: const TextStyle(color: Colors.grey, fontSize: 14)),
        ),
      );
    }
    return ListView.builder(
      itemCount: positions.length,
      itemBuilder: (context, index) {
        final pilot = positions[index] as Map<String, dynamic>;
        final phase = pilot['flight_phase']?.toString() ?? 'Unknown';
        final phaseColor = phase.toLowerCase().contains('cruise') || phase.toLowerCase().contains('reiseflug') ? const Color(0xFF00ff66) : const Color(0xFFffcc00);
        return Card(
          margin: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          color: const Color(0xFF12161f),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8), side: const BorderSide(color: Color(0xFF2a3545), width: 1)),
          child: Padding(
            padding: const EdgeInsets.all(14.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(child: Text('✈️ ${pilot['pilot_name'] ?? pilot['pilot'] ?? 'Pilot'}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: Color(0xFF0088ff)))),
                    Text(phase.toUpperCase(), style: TextStyle(color: phaseColor, fontWeight: FontWeight.bold, fontFamily: 'monospace', letterSpacing: 0.5)),
                  ],
                ),
                const SizedBox(height: 8),
                Text('${pilot['aircraft_model'] ?? pilot['aircraft'] ?? 'Aircraft'} • ${MobileLocalization.tr('fids.route', lang)} ${pilot['current_icao'] ?? '—'}', style: const TextStyle(color: Colors.grey, fontSize: 13)),
                const SizedBox(height: 6),
                Text('${pilot['altitude'] ?? 0} ft • ${pilot['ground_speed']?.toString() ?? '0'} kt', style: const TextStyle(color: Color(0xFF33ccff), fontSize: 12, fontFamily: 'monospace')),
                const SizedBox(height: 4),
                Text('🧭 ${pilot['heading'] ?? 0}° • ${pilot['route'] ?? '—'}', style: const TextStyle(color: Colors.white70, fontSize: 12)),
              ],
            ),
          ),
        );
      },
    );
  }
}

class MobileJobsTab extends StatelessWidget {
  final String lang;
  final List<dynamic> jobs;
  final Future<void> Function(int) onAccept;
  const MobileJobsTab({Key? key, required this.lang, required this.jobs, required this.onAccept}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    if (jobs.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Text(MobileLocalization.tr('jobs.empty', lang), textAlign: TextAlign.center, style: const TextStyle(color: Colors.grey, fontSize: 14)),
        ),
      );
    }
    return ListView.builder(
      itemCount: jobs.length,
      itemBuilder: (context, index) {
        final job = jobs[index] as Map<String, dynamic>;
        final id = int.tryParse('${job['job_id'] ?? job['id'] ?? 0}') ?? 0;
        return Card(
          margin: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          color: const Color(0xFF10131a),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8), side: const BorderSide(color: Color(0xFF2a3545), width: 1)),
          child: Padding(
            padding: const EdgeInsets.all(14.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${job['departure_icao'] ?? '---'} → ${job['arrival_icao'] ?? '---'}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: Color(0xFFd4af37))),
                const SizedBox(height: 6),
                Text('${job['job_type'] ?? 'Charter'} • ${job['distance_nm']?.toString() ?? '0'} NM', style: const TextStyle(color: Colors.grey, fontSize: 13)),
                const SizedBox(height: 6),
                Text('${MobileLocalization.tr('account.credits', lang)}: ${job['payout_credits']?.toString() ?? '0'}', style: const TextStyle(color: Colors.white70, fontSize: 13)),
                const SizedBox(height: 10),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('${job['cargo_weight_lbs']?.toString() ?? '0'} lb', style: const TextStyle(color: Colors.grey, fontSize: 12)),
                    ElevatedButton(
                      onPressed: () => onAccept(id),
                      style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFFd4af37), foregroundColor: Colors.black),
                      child: Text(MobileLocalization.tr('jobs.accept', lang)),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class MobileAccountTab extends StatelessWidget {
  final String lang;
  final Map<String, dynamic>? accountData;
  final String statusMessage;
  final Future<void> Function() onRefresh;
  const MobileAccountTab({Key? key, required this.lang, required this.accountData, required this.statusMessage, required this.onRefresh}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    if (accountData == null) {
      return Center(child: Text(statusMessage.isNotEmpty ? statusMessage : MobileLocalization.tr('account.loading', lang), style: const TextStyle(color: Colors.grey)));
    }
    final alliance = accountData?['alliance_summary'] as Map<String, dynamic>?;
    return RefreshIndicator(
      onRefresh: onRefresh,
      child: ListView(
        padding: const EdgeInsets.all(14),
        children: [
          if (statusMessage.isNotEmpty) ...[
            Card(
              color: const Color(0xFF10131a),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Text(statusMessage, style: const TextStyle(color: Colors.amberAccent)),
              ),
            ),
            const SizedBox(height: 12),
          ],
          _buildMetricCard(lang, 'account.credits', accountData?['credits']?.toString() ?? '0'),
          _buildMetricCard(lang, 'account.xp', accountData?['xp']?.toString() ?? '0'),
          _buildMetricCard(lang, 'account.rep', accountData?['reputation']?.toString() ?? '0'),
          _buildMetricCard(lang, 'account.loan', accountData?['loan_debt']?.toString() ?? '0'),
          _buildMetricCard(lang, 'account.tax', accountData?['credit_score']?.toString() ?? '0'),
          const SizedBox(height: 16),
          Text(MobileLocalization.tr('account.alliance', lang), style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Color(0xFFd4af37))),
          const SizedBox(height: 8),
          Card(
            color: const Color(0xFF10131a),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: alliance == null || alliance['in_alliance'] != true
                  ? Text(MobileLocalization.tr('account.no_alliance', lang), style: const TextStyle(color: Colors.white70))
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('${MobileLocalization.tr('account.alliance', lang)}: ${alliance['alliance_name'] ?? '—'}', style: const TextStyle(color: Colors.white)),
                        const SizedBox(height: 4),
                        Text('${MobileLocalization.tr('alliance.role', lang)}: ${alliance['role'] ?? '—'}', style: const TextStyle(color: Colors.grey)),
                        const SizedBox(height: 4),
                        Text('${MobileLocalization.tr('alliance.pool', lang)}: ${alliance['alliance_credits']?.toString() ?? '0'}', style: const TextStyle(color: Colors.grey)),
                        const SizedBox(height: 4),
                        Text('${MobileLocalization.tr('alliance.tax', lang)}: ${alliance['tax_pct']?.toString() ?? '0'}%', style: const TextStyle(color: Colors.grey)),
                      ],
                    ),
            ),
          ),
          const SizedBox(height: 12),
          ElevatedButton(onPressed: onRefresh, style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF0088ff)), child: Text(MobileLocalization.tr('refresh', lang))),
        ],
      ),
    );
  }

  Widget _buildMetricCard(String lang, String label, String value) {
    return Card(
      color: const Color(0xFF10131a),
      margin: const EdgeInsets.only(bottom: 12),
      child: ListTile(
        title: Text(MobileLocalization.tr(label, lang), style: const TextStyle(color: Colors.white)),
        trailing: Text(value, style: const TextStyle(color: Color(0xFFd4af37), fontWeight: FontWeight.bold)),
      ),
    );
  }
}

class MobileAllianceTab extends StatefulWidget {
  final String lang;
  final Map<String, dynamic>? accountData;
  final Future<void> Function(String) createAlliance;
  final Future<void> Function(String) joinAlliance;
  const MobileAllianceTab({Key? key, required this.lang, required this.accountData, required this.createAlliance, required this.joinAlliance}) : super(key: key);

  @override
  State<MobileAllianceTab> createState() => _MobileAllianceTabState();
}

class _MobileAllianceTabState extends State<MobileAllianceTab> {
  final TextEditingController _createController = TextEditingController();
  final TextEditingController _joinController = TextEditingController();
  bool _busy = false;

  Future<void> _handleCreate() async {
    if (_createController.text.trim().isEmpty) return;
    setState(() => _busy = true);
    await widget.createAlliance(_createController.text.trim());
    setState(() => _busy = false);
  }

  Future<void> _handleJoin() async {
    if (_joinController.text.trim().isEmpty) return;
    setState(() => _busy = true);
    await widget.joinAlliance(_joinController.text.trim());
    setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final alliance = widget.accountData?['alliance_summary'] as Map<String, dynamic>?;
    return ListView(
      padding: const EdgeInsets.all(14),
      children: [
        if (alliance != null && alliance['in_alliance'] == true) ...[
          Text(MobileLocalization.tr('alliance.title', widget.lang), style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Color(0xFFd4af37))),
          const SizedBox(height: 12),
          _buildDetail('account.alliance', alliance['alliance_name'] ?? '—'),
          _buildDetail('account.alliance_id', alliance['alliance_id']?.toString() ?? '—'),
          _buildDetail('alliance.role', alliance['role'] ?? '—'),
          _buildDetail('alliance.pool', alliance['alliance_credits']?.toString() ?? '0'),
          _buildDetail('alliance.tax', '${alliance['tax_pct']?.toString() ?? '0'}%'),
          const SizedBox(height: 10),
          Text(MobileLocalization.tr('alliance.leases', widget.lang), style: const TextStyle(color: Colors.white70, fontSize: 14)),
          ...((alliance['route_leases'] as List<dynamic>?) ?? []).map((lease) {
            final item = lease as Map<String, dynamic>;
            final expires = DateTime.fromMillisecondsSinceEpoch((item['expires_ts']?.toInt() ?? 0) * 1000).toLocal();
            return Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text('${item['icao'] ?? '----'} • ${item['credits']?.toString() ?? '0'} credits • ${expires.toString().split(' ').first}', style: const TextStyle(color: Colors.grey, fontSize: 12)),
            );
          }),
        ] else ...[
          Card(
            color: const Color(0xFF10131a),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Text(MobileLocalization.tr('account.no_alliance', widget.lang), style: const TextStyle(color: Colors.white70)),
            ),
          ),
          const SizedBox(height: 18),
          TextField(controller: _createController, decoration: InputDecoration(labelText: MobileLocalization.tr('account.alliance_name', widget.lang), border: const OutlineInputBorder())),
          const SizedBox(height: 12),
          ElevatedButton(onPressed: _busy ? null : _handleCreate, style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFFd4af37)), child: Text(MobileLocalization.tr('account.create_btn', widget.lang))),
          const SizedBox(height: 24),
          TextField(controller: _joinController, decoration: InputDecoration(labelText: MobileLocalization.tr('account.alliance_id', widget.lang), border: const OutlineInputBorder())),
          const SizedBox(height: 12),
          ElevatedButton(onPressed: _busy ? null : _handleJoin, style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF0088ff)), child: Text(MobileLocalization.tr('account.join_btn', widget.lang))),
        ],
      ],
    );
  }

  Widget _buildDetail(String labelKey, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(MobileLocalization.tr(labelKey, widget.lang), style: const TextStyle(color: Colors.grey)),
          Expanded(child: Text(value, textAlign: TextAlign.right, style: const TextStyle(color: Colors.white))),
        ],
      ),
    );
  }
}
