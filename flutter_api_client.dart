import 'dart:convert';
import 'package:http/http.dart' as http;

class Haowu999Asset {
  final String name;
  final String ticker;
  final double score;
  final double ahr999;
  final double r2;
  final String signal;
  final double weight;

  Haowu999Asset({
    required this.name,
    required this.ticker,
    required this.score,
    required this.ahr999,
    required this.r2,
    required this.signal,
    required this.weight,
  });

  factory Haowu999Asset.fromJson(Map<String, dynamic> json) {
    return Haowu999Asset(
      name: json['name_cn'] ?? json['name'],
      ticker: json['ticker'],
      score: (json['snr'] ?? json['score'] ?? 0.0).toDouble(),
      ahr999: (json['ahr999'] ?? 0.0).toDouble(),
      r2: (json['r2'] ?? 0.0).toDouble(),
      signal: json['signal'],
      weight: (json['ahr999'] ?? 0.0) < 0.45 ? 3.0 : ((json['ahr999'] ?? 0.0) < 1.2 ? 1.0 : 0.0),
    );
  }
}

class Haowu999Service {
  static const String apiUrl = "https://raw.githubusercontent.com/wuhao007/haowu999/main/latest_data.json";

  Future<List<Haowu999Asset>> fetchSignals() async {
    final response = await http.get(Uri.parse(apiUrl));
    if (response.statusCode == 200) {
      List<dynamic> body = jsonDecode(response.body);
      return body.map((dynamic item) => Haowu999Asset.fromJson(item)).toList();
    } else {
      throw Exception("Failed to load quant signals");
    }
  }
}
