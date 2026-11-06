import 'package:flutter/material.dart';

void main() {
  runApp(const BeveltryApp());
}

class BeveltryApp extends StatelessWidget {
  const BeveltryApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Beveltry',
      theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: Colors.teal)),
      home: const Scaffold(
        body: Center(child: Text('Beveltry')),
      ),
    );
  }
}
