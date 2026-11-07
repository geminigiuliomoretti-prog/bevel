import 'package:flutter/material.dart';

import 'screens/dashboard_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const BeveltryApp());
}

class BeveltryApp extends StatelessWidget {
  const BeveltryApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Beveltry',
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.teal,
          brightness: Brightness.dark,
        ),
      ),
      home: const DashboardScreen(),
    );
  }
}
