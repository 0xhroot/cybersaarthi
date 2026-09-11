package io.cybersaarthi.fieldagent.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/**
 * Deliberate CyberSaarthi brand: deep navy surfaces, steel-blue actions and a
 * single amber signal accent. Dynamic colour is disabled on purpose so the
 * brand identity survives across devices and field conditions.
 */
private val LightColors = lightColorScheme(
    primary = Color(0xFF1F5A8A),
    onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFD2E4F6),
    onPrimaryContainer = Color(0xFF0B2940),
    secondary = Color(0xFF34576F),
    onSecondary = Color(0xFFFFFFFF),
    secondaryContainer = Color(0xFFC6DBE9),
    onSecondaryContainer = Color(0xFF0F2B3B),
    tertiary = Color(0xFF8D5E00),
    onTertiary = Color(0xFFFFFFFF),
    tertiaryContainer = Color(0xFFF2D390),
    onTertiaryContainer = Color(0xFF2B1E00),
    error = Color(0xFFBA1A1A),
    onError = Color(0xFFFFFFFF),
    errorContainer = Color(0xFFFFDAD6),
    onErrorContainer = Color(0xFF410002),
    background = Color(0xFFF7F8FA),
    onBackground = Color(0xFF171B20),
    surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF171B20),
    surfaceVariant = Color(0xFFDEE3EA),
    onSurfaceVariant = Color(0xFF43474E),
    outline = Color(0xFF73777F),
    surfaceTint = Color(0xFF1F5A8A)
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF8FC1E9),
    onPrimary = Color(0xFF00324F),
    primaryContainer = Color(0xFF0B496E),
    onPrimaryContainer = Color(0xFFCFE3F6),
    secondary = Color(0xFFA4C3D7),
    onSecondary = Color(0xFF0A3449),
    secondaryContainer = Color(0xFF28495E),
    onSecondaryContainer = Color(0xFFC0D9EA),
    tertiary = Color(0xFFF4BE5D),
    onTertiary = Color(0xFF4A3400),
    tertiaryContainer = Color(0xFF6D4E00),
    onTertiaryContainer = Color(0xFFFFDEAA),
    error = Color(0xFFFFB4AB),
    onError = Color(0xFF690005),
    errorContainer = Color(0xFF93000A),
    onErrorContainer = Color(0xFFFFDAD6),
    background = Color(0xFF0E151B),
    onBackground = Color(0xFFE1E2E6),
    surface = Color(0xFF11181F),
    onSurface = Color(0xFFE1E2E6),
    surfaceVariant = Color(0xFF43474E),
    onSurfaceVariant = Color(0xFFC2C7CE),
    outline = Color(0xFF8C9199),
    surfaceTint = Color(0xFF8FC1E9)
)

@Composable
fun CyberSaarthiTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        content = content
    )
}