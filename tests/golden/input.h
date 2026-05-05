/**
 * @brief A primary class.
 *
 * Demonstrates the full @nb tag surface for classes.
 *
 * @nb
 * @nb_intrusive_ptr
 * @nb_dynamic_attr
 */
class Test
{
public:
    /**
     * @brief Default-construct.
     * @nb
     */
    Test();

    /**
     * @brief Construct from an int reference.
     * @param a the input
     * @nb
     */
    Test(int &a);

    /**
     * Complex parameters.
     *
     * @param a a
     * @param b b
     * @param c c
     * @nb
     */
    void nontrivial_params(std::vector<std::string> &a, double *b = nullptr,
                           std::vector<int> &c = std::vector<int>());

    /**
     * @brief An overloaded function.
     * @param a First param
     * @nb
     */
    void overload(double &a);

    /**
     * @brief An overloaded function.
     * @param b Alternate param
     * @nb
     */
    void overload(int b);

    /**
     * @brief A magic method.
     * @nb
     * @nb_name __magic__
     */
    void magic();

    /**
     * @brief Static read-only property.
     * @nb
     * @nb_prop_ro static_prop
     */
    static int static_prop();
};

/**
 * @brief A second class with multiple bases and a custom factory.
 * @nb
 * @nb_inherit Test
 * @nb_final
 */
class Test2
{
public:
    /**
     * @brief Construct via factory.
     * @param a the value
     * @return constructed Test2
     * @nb
     * @nb_new
     */
    static nb::ref<Test2> make(int a);

    /**
     * @brief Get the name.
     * @return the name
     * @nb
     * @nb_prop_rw name
     */
    std::string get_name();

    /**
     * @brief Set the name.
     * @param name the new name
     * @nb
     * @nb_prop_rw name
     */
    void set_name(std::string name);

    /**
     * @brief Get a read-only prop.
     * @nb
     * @nb_prop_ro prop
     */
    int get_prop();

    /**
     * @brief Iterate this object.
     * @return iterator
     * @nb
     * @nb_name __iter__
     * @nb_extra nb::keep_alive<0, 1>()
     */
    auto iter() -> nb::typed<nb::iterator, ref<Test>&>;
};

/**
 * @brief A free function.
 * @param a Hello
 * @param b Bye
 * @return result
 * @nb
 */
void freefn(int a, double b);

/**
 * @brief An overridden-doc function.
 * @nb
 * @nb_doc Custom Python docstring.
 */
int free_return_simple();

/**
 * @brief An enum with values that have docstrings.
 * @nb
 * @nb_arithmetic
 */
enum class TestEnum : std::uint8_t
{
    /**
     * @brief A car.
     */
    CAR,
    /**
     * @brief A truck.
     */
    TRUCK,
    BIKE
};

/**
 * @brief An unbound enum.
 */
enum class DontBind
{
    DO,
    NOT,
    BIND
};
