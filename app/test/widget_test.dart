import 'package:beveltry/main.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('mostra il nome Beveltry', (tester) async {
    await tester.pumpWidget(const BeveltryApp());
    expect(find.text('Beveltry'), findsOneWidget);
  });
}
