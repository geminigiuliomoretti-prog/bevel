plugins {
    kotlin("jvm")
}

dependencies {
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.9.0")
    testImplementation("junit:junit:4.13.2")
}

kotlin { jvmToolchain(17) }

tasks.test {
    useJUnit()
    testLogging { showStandardStreams = true }
}
